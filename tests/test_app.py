import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from fakes import HIJACKED_RUN, HONEST_RUN, RESISTED_RUN, ScriptedModel, say
from google.genai import errors as genai_errors

import app
from interlock.intent import Assessment, StubAssessor
from interlock.trace import Signer

KEY = "test-key-not-real"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No test may touch devnet, whatever the developer's environment holds."""
    monkeypatch.setattr(app, "DEVNET", None)
    monkeypatch.setattr(app, "RPC", None)


def _fake_live(monkeypatch, turns, assessment=Assessment(True, "matches")):
    monkeypatch.setattr(app, "GeminiAgentModel", lambda key: ScriptedModel(*turns))
    monkeypatch.setattr(app, "GeminiAssessor", lambda key: StubAssessor(assessment))


@pytest.mark.parametrize(
    "name,expected", [("clean", True), ("injected", False), ("semantic", True)]
)
def test_decide_returns_the_expected_verdict(name, expected):
    assert app.decide(name)["allowed"] is expected


def test_decide_payload_is_json_serialisable():
    assert json.loads(json.dumps(app.decide("injected")))["allowed"] is False


def test_decide_exposes_the_typed_instruction_chain():
    chain = app.decide("injected")["scenario"]["instruction_chain"]
    assert [s["trust"] for s in chain] == ["principal", "tool", "content", "agent"]


def test_decide_rejects_an_unknown_scenario():
    with pytest.raises(KeyError):
        app.decide("nope")


def test_replay_reports_settlement_honestly():
    assert app.decide("clean")["settlement"]["status"] == "not_configured"
    assert app.decide("injected")["settlement"]["status"] == "not_sent"


def test_replay_runs_layer_three_only_with_a_key(monkeypatch):
    monkeypatch.setattr(app, "GeminiAssessor", lambda key: StubAssessor(Assessment(False, "Dubai")))
    assert app.decide("semantic")["allowed"] is True
    assert app.decide("semantic", KEY)["allowed"] is False


def test_live_honest_run_is_allowed(monkeypatch):
    _fake_live(monkeypatch, HONEST_RUN)
    status, body = app.handle_run({"listing": "honest"}, KEY)
    assert status == 200
    assert body["mode"] == "live"
    assert body["allowed"] is True
    assert body["scenario"]["instruction_chain"][3]["trust"] == "content"


def test_live_hijacked_run_is_denied_and_never_settled(monkeypatch):
    _fake_live(monkeypatch, HIJACKED_RUN)
    status, body = app.handle_run({"listing": "poisoned"}, KEY)
    assert status == 200
    assert body["allowed"] is False
    assert body["settlement"]["status"] == "not_sent"
    assert KEY not in json.dumps(body)


def test_live_run_without_a_payment_has_no_decision(monkeypatch):
    _fake_live(monkeypatch, (say("Nothing fits."),))
    status, body = app.handle_run({"listing": "honest"}, KEY)
    assert status == 200
    assert body["allowed"] is None
    assert body["settlement"] is None
    assert "Nothing fits." in body["agent_detail"]


def test_live_run_needs_a_key_and_a_known_listing():
    assert app.handle_run({"listing": "honest"}, None)[0] == 400
    assert app.handle_run({"listing": "sneaky"}, KEY)[0] == 400


@pytest.mark.parametrize("code,expected", [(429, 429), (400, 401), (403, 401), (500, 502)])
def test_gemini_errors_map_to_clear_statuses(monkeypatch, code, expected):
    def boom(model, listing):
        raise genai_errors.APIError(code, {"error": {"code": code, "message": "nope", "status": "X"}})

    monkeypatch.setattr(app, "GeminiAgentModel", lambda key: None)
    monkeypatch.setattr(app, "run_agent", boom)
    status, body = app.handle_run({"listing": "honest"}, KEY)
    assert status == expected
    assert "error" in body


def test_verify_accepts_a_real_decision_and_rejects_tampering():
    body = app.decide("clean")
    decision = {k: body[k] for k in ("payment_id", "allowed", "issued_at", "checks", "payment", "signature", "public_key")}
    assert app.handle_verify(decision, None) == (200, {"valid": True, "public_key": app.SIGNER.public_key_hex})

    tampered = json.loads(json.dumps(decision))
    tampered["payment"]["amount"] = "5400"
    assert app.handle_verify(tampered, None)[1]["valid"] is False


def test_verify_rejects_a_decision_signed_by_another_key():
    other = Signer.generate()
    body = app.decide("clean")
    from interlock.trace import payload_from_decision

    forged = {**body, "public_key": other.public_key_hex}
    forged["signature"] = other.sign(payload_from_decision(forged))
    assert app.handle_verify(forged, None)[1]["valid"] is False


def test_verify_rejects_a_malformed_body():
    assert app.handle_verify({"allowed": True}, None)[0] == 400
    assert app.handle_verify({**app.decide("clean"), "signature": "zz"}, None)[0] == 400


def test_production_refuses_to_start_without_a_signing_key():
    with pytest.raises(RuntimeError):
        app.load_signer({"VERCEL_ENV": "production"})
    key = Signer.generate()
    assert app.load_signer({"INTERLOCK_SIGNING_KEY": key.private_key_hex}).public_key_hex == key.public_key_hex
    assert app.load_signer({}).public_key_hex


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), app.handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _post(url, payload, headers=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_pasted_key_is_stripped_before_use(server, monkeypatch):
    seen = {}

    def fake_run_live(listing, key):
        seen["key"] = key
        return {"mode": "live"}

    monkeypatch.setattr(app, "run_live", fake_run_live)
    status, _ = _post(server + "/api/run", {"listing": "honest"}, {"X-Gemini-Key": "  test-key \t"})
    assert status == 200
    assert seen["key"] == "test-key"


def test_listing_pages_and_public_key_are_served(server):
    with urllib.request.urlopen(server + "/fares/lhr-540?variant=poisoned") as response:
        assert "partner agency" in response.read().decode()
    with urllib.request.urlopen(server + "/api/public-key") as response:
        assert json.loads(response.read())["public_key"] == app.SIGNER.public_key_hex
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(server + "/fares/nope")


def test_unknown_post_route_and_bad_json_are_rejected(server):
    assert _post(server + "/api/nope", {})[0] == 404
    request = urllib.request.Request(
        server + "/api/authorize", data=b"{not json", headers={"Content-Type": "application/json"}, method="POST"
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request)
    assert exc.value.code == 400


@pytest.mark.parametrize("code,expected", [(400, 401), (403, 401), (429, 429)])
def test_replay_with_a_rejected_key_reports_the_key_not_a_denial(monkeypatch, code, expected):
    class Rejecting:
        def assess(self, mandate, payment):
            raise genai_errors.APIError(code, {"error": {"code": code, "message": "nope", "status": "X"}})

    monkeypatch.setattr(app, "GeminiAssessor", lambda key: Rejecting())
    status, body = app.handle_authorize({"scenario": "clean"}, KEY)
    assert status == expected
    assert "error" in body
    assert "allowed" not in body


def test_poisoned_runs_say_whether_the_agent_was_hijacked(monkeypatch):
    _fake_live(monkeypatch, HIJACKED_RUN)
    assert app.handle_run({"listing": "poisoned"}, KEY)[1]["agent_outcome"] == "hijacked"


def test_a_resisting_agent_is_allowed(monkeypatch):
    """The live poisoned page only redirects; an agent that ignores it and pays the
    quoted fare is doing its job, and Interlock lets the payment through."""
    _fake_live(monkeypatch, RESISTED_RUN)
    status, body = app.handle_run({"listing": "poisoned"}, KEY)
    assert body["agent_outcome"] == "resisted"
    assert body["allowed"] is True


def test_honest_runs_carry_no_injection_outcome(monkeypatch):
    _fake_live(monkeypatch, HONEST_RUN)
    assert "agent_outcome" not in app.handle_run({"listing": "honest"}, KEY)[1]


def test_replay_says_layer_three_was_off_without_a_key():
    assert app.decide("semantic")["layer3"] == "off"


def test_replay_says_layer_three_ran_with_a_key(monkeypatch):
    monkeypatch.setattr(app, "GeminiAssessor", lambda key: StubAssessor(Assessment(True, "ok")))
    assert app.decide("clean", KEY)["layer3"] == "ran"


def test_layer_three_is_not_reached_when_an_earlier_layer_denies(monkeypatch):
    monkeypatch.setattr(app, "GeminiAssessor", lambda key: StubAssessor(Assessment(True, "ok")))
    assert app.decide("injected", KEY)["layer3"] == "not_reached"


def test_live_runs_report_layer_three(monkeypatch):
    _fake_live(monkeypatch, HONEST_RUN)
    assert app.handle_run({"listing": "honest"}, KEY)[1]["layer3"] == "ran"


def _rejecting_key_error():
    return genai_errors.APIError(
        400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}}
    )


def test_a_rejected_key_in_replay_says_how_to_replay_without_it(monkeypatch):
    class Rejecting:
        def assess(self, mandate, payment):
            raise _rejecting_key_error()

    monkeypatch.setattr(app, "GeminiAssessor", lambda key: Rejecting())
    error = app.handle_authorize({"scenario": "clean"}, KEY)[1]["error"]
    assert "Clear the key" in error
    assert "use Replay mode" not in error
    assert ".." not in error


def test_a_rejected_key_in_live_points_to_replay(monkeypatch):
    def boom(model, listing):
        raise _rejecting_key_error()

    monkeypatch.setattr(app, "GeminiAssessor", lambda key: None)
    monkeypatch.setattr(app, "GeminiAgentModel", lambda key: None)
    monkeypatch.setattr(app, "run_agent", boom)
    error = app.handle_run({"listing": "honest"}, KEY)[1]["error"]
    assert "Replay mode" in error
    assert ".." not in error


def test_only_known_paths_are_served(server):
    for path in ("/robots.txt", "/favicon.ico", "/api/authorize", "/fares/", "/nope"):
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(server + path)
        assert exc.value.code == 404, path
    with urllib.request.urlopen(server + "/") as response:
        assert "<html" in response.read().decode()
    with urllib.request.urlopen(server + "/favicon.svg") as response:
        assert response.headers["Content-Type"].startswith("image/svg+xml")
