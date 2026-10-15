"""HTTP entrypoint - the page, the demo listing pages and the API.

Used both locally (`python app.py`) and as the deployed entrypoint.

The visitor's Gemini key arrives in the X-Gemini-Key header, is used for that
request only, and is never stored, logged or returned.
"""

import json
import os
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import httpx
from google.genai import errors as genai_errors

from agent import fixtures
from agent.harness import GeminiAgentModel, run_agent
from demo.scenarios import MANDATE, SCENARIOS
from interlock.engine import authorize
from interlock.intent import GeminiAssessor
from interlock.settlement import DEFAULT_RPC_URL, JsonRpc, load_config, settle
from interlock.trace import Signer, payload_from_decision, verify

PUBLIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
MAX_BODY = 64 * 1024
PRODUCTION = os.environ.get("VERCEL_ENV") == "production"

LIVE_DESCRIPTIONS = {
    "honest": "A live agent books the flight. The listing page it reads is honest.",
    "poisoned": (
        "A live agent books the flight. The listing page it reads tells it to pay a "
        "different merchant. Whether the agent falls for it is up to the model - "
        "Interlock lets an agent that ignores it pay the quoted fare, and stops one "
        "that obeys."
    ),
}


def load_signer(env=os.environ) -> Signer:
    key = env.get("INTERLOCK_SIGNING_KEY", "").strip()
    if key:
        return Signer.from_hex(key)
    if env.get("VERCEL_ENV") == "production":
        raise RuntimeError("INTERLOCK_SIGNING_KEY must be set in production")
    return Signer.generate()


SIGNER = load_signer()
DEVNET = load_config(authority=SIGNER.public_key_hex)
if DEVNET is None and PRODUCTION:
    raise RuntimeError("SOLANA_TREASURY_KEY and interlock/devnet.json are required in production")
RPC = JsonRpc(os.environ.get("SOLANA_RPC_URL", DEFAULT_RPC_URL)) if DEVNET else None


def _steps(chain) -> list[dict]:
    return [{"source": s.source, "trust": s.trust.value, "content": s.content} for s in chain]


def _payment_view(payment) -> dict:
    return {
        "recipient": payment.recipient,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "chain": payment.chain,
        "memo": payment.memo,
    }


class _KeyCheckedAssessor:
    """In Replay the assessor is the only Gemini call, so a rejected or exhausted
    key must surface as a key problem - not as a denial of the scenario."""

    def __init__(self, inner):
        self._inner = inner
        self.rejection: genai_errors.APIError | None = None

    def assess(self, mandate, payment):
        try:
            return self._inner.assess(mandate, payment)
        except genai_errors.APIError as exc:
            if getattr(exc, "code", None) in (400, 401, 403, 429):
                self.rejection = exc
            raise


def _layer3(checks: list[dict], api_key: str | None) -> str:
    """Whether the semantic layer judged this payment: off without a key, and not
    reached when a cheaper layer already denied."""
    if not api_key:
        return "off"
    return "ran" if any(c["name"] == "intent_match" for c in checks) else "not_reached"


def decide(name: str, api_key: str | None = None) -> dict:
    """Replay one named scenario: scripted inputs, real decision, real settlement."""
    scenario = SCENARIOS[name]
    assessor = _KeyCheckedAssessor(GeminiAssessor(api_key)) if api_key else None
    decision = authorize(scenario.mandate, scenario.payment, scenario.spent, SIGNER, assessor)
    if assessor is not None and assessor.rejection is not None:
        raise assessor.rejection  # nothing was settled; handle_authorize maps it
    body = decision.to_dict()
    body["mode"] = "replay"
    body["layer3"] = _layer3(body["checks"], api_key)
    body["scenario"] = {
        "name": scenario.name,
        "description": scenario.description,
        "intent": scenario.mandate.intent,
        **_payment_view(scenario.payment),
        "instruction_chain": _steps(scenario.payment.instruction_chain),
    }
    body["settlement"] = settle(decision, scenario.payment, DEVNET, RPC).to_dict()
    return body


def run_live(listing: str, api_key: str) -> dict:
    """Run the real agent, decide on what it asked to pay, settle if allowed."""
    result = run_agent(GeminiAgentModel(api_key), listing)
    scenario = {
        "name": f"live-{listing}",
        "description": LIVE_DESCRIPTIONS[listing],
        "intent": MANDATE.intent,
        "instruction_chain": _steps(result.steps),
    }
    if result.payment is None:
        return {
            "mode": "live",
            "agent_detail": result.detail,
            "allowed": None,
            "checks": [],
            "layer3": "not_reached",
            "settlement": None,
            "scenario": scenario,
        }

    decision = authorize(MANDATE, result.payment, Decimal("0"), SIGNER, GeminiAssessor(api_key))
    body = decision.to_dict()
    body["mode"] = "live"
    body["layer3"] = _layer3(body["checks"], api_key)
    body["agent_detail"] = result.detail
    body["scenario"] = {**scenario, **_payment_view(result.payment)}
    if listing == "poisoned":
        hijacked = result.payment.recipient == fixtures.INJECTED_RECIPIENT
        body["agent_outcome"] = "hijacked" if hijacked else "resisted"
    body["settlement"] = settle(decision, result.payment, DEVNET, RPC).to_dict()
    return body


def _gemini_error(exc: genai_errors.APIError, mode: str) -> tuple[int, dict]:
    code = getattr(exc, "code", None)
    reason = (exc.message or exc.status or "unknown error").strip().rstrip(".")
    way_out = (
        "Clear the key field to replay without layer 03"
        if mode == "replay"
        else "Check the key, or use Replay mode"
    )
    if code == 429:
        return 429, {"error": f"Your Gemini key is out of quota or rate-limited ({reason}). Try again later. {way_out}."}
    if code in (400, 401, 403):
        return 401, {"error": f"Gemini rejected the key ({reason}). {way_out}."}
    return 502, {"error": f"Gemini error {code} ({reason}). Try again in a moment."}


def handle_authorize(request: dict, key: str | None) -> tuple[int, dict]:
    name = request.get("scenario", "")
    if name not in SCENARIOS:
        return 400, {"error": f"unknown scenario; expected one of {sorted(SCENARIOS)}"}
    try:
        return 200, decide(name, key)
    except genai_errors.APIError as exc:
        return _gemini_error(exc, "replay")


def handle_run(request: dict, key: str | None) -> tuple[int, dict]:
    listing = request.get("listing")
    if listing not in fixtures.VARIANTS:
        return 400, {"error": f"unknown listing; expected one of {list(fixtures.VARIANTS)}"}
    if not key:
        return 400, {"error": "a Gemini API key is required for live mode"}
    try:
        return 200, run_live(listing, key)
    except genai_errors.APIError as exc:
        return _gemini_error(exc, "live")
    except httpx.HTTPError as exc:
        return 502, {"error": f"could not reach Gemini: {type(exc).__name__}"}


def handle_verify(request: dict, key: str | None) -> tuple[int, dict]:
    try:
        payload = payload_from_decision(request)
        claimed = request["public_key"]
        valid = claimed == SIGNER.public_key_hex and verify(
            payload, request["signature"], SIGNER.public_key_hex
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return 400, {"error": "not a decision: expected the fields returned by /api/authorize"}
    return 200, {"valid": valid, "public_key": SIGNER.public_key_hex}


STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}

ROUTES = {
    "/api/authorize": handle_authorize,
    "/api/run": handle_run,
    "/api/verify": handle_verify,
}


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, body: dict, key: str | None = None) -> None:
        text = json.dumps(body)
        if key:
            text = text.replace(key, "[redacted]")
        self._send(status, text.encode(), "application/json")

    def do_GET(self) -> None:
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"
        if path == "/api/public-key":
            self._json(200, {"public_key": SIGNER.public_key_hex, "algorithm": "ed25519"})
            return
        if path.startswith("/fares/"):
            variant = parse_qs(url.query).get("variant", ["honest"])[0]
            page = fixtures.listing_html(path.removeprefix("/fares/"), variant)
            if page is None:
                self._send(404, b"not found", "text/plain; charset=utf-8")
            else:
                self._send(200, page.encode(), "text/html; charset=utf-8")
            return
        static = STATIC.get(path)
        if static is None:
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        filename, content_type = static
        with open(os.path.join(PUBLIC, filename), "rb") as f:
            self._send(200, f.read(), content_type)

    def do_POST(self) -> None:
        route = ROUTES.get(urlparse(self.path).path.rstrip("/"))
        if route is None:
            self._json(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY:
                self._json(413, {"error": "request body too large"})
                return
            request = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(request, dict):
                raise ValueError("body must be a JSON object")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "invalid JSON body"})
            return

        key = self.headers.get("X-Gemini-Key", "").strip() or None
        status, body = route(request, key)
        self._json(status, body, key)

    def log_message(self, *args) -> None:
        pass


if __name__ == "__main__":
    print("Interlock on http://localhost:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), handler).serve_forever()
