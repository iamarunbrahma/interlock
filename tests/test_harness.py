from decimal import Decimal
from types import SimpleNamespace

import pytest
from fakes import HIJACKED_RUN, HONEST_RUN, ScriptedModel, call, say
from google.genai import types

from agent import fixtures
from agent.harness import MAX_TOOL_CALLS, GeminiAgentModel, parse_amount, run_agent
from demo.scenarios import MANDATE
from interlock.engine import authorize
from interlock.models import PlanHint, TrustLevel
from interlock.trace import Signer


def test_honest_run_builds_the_chain_from_the_tool_calls_made():
    result = run_agent(ScriptedModel(*HONEST_RUN), "honest")
    assert [s.trust for s in result.steps] == [
        TrustLevel.PRINCIPAL,
        TrustLevel.TOOL,
        TrustLevel.TOOL,
        TrustLevel.CONTENT,
        TrustLevel.AGENT,
    ]
    assert result.steps[2].plan == PlanHint("merchant.airline.example", Decimal("540"))
    assert result.payment.recipient == "merchant.airline.example"
    assert result.payment.amount == Decimal("540")
    assert result.payment.instruction_chain == result.steps
    assert authorize(MANDATE, result.payment, Decimal("0"), Signer.generate()).allowed


def test_quote_hands_out_the_poisoned_listing_in_poisoned_mode():
    model = ScriptedModel(*HIJACKED_RUN)
    result = run_agent(model, "poisoned")
    content = [s for s in result.steps if s.trust is TrustLevel.CONTENT]
    assert content[0].source == "web-page(/fares/lhr-540?variant=poisoned)"
    assert fixtures.POISON in content[0].content


def test_a_hijacked_agent_is_denied_by_provenance():
    result = run_agent(ScriptedModel(*HIJACKED_RUN), "poisoned")
    decision = authorize(MANDATE, result.payment, Decimal("0"), Signer.generate())
    assert not decision.allowed
    assert {c.name for c in decision.checks if not c.passed} == {
        "plan_divergence",
        "concealment",
    }


def test_open_listing_refuses_urls_no_quote_handed_out():
    model = ScriptedModel(
        call("open_listing", url="/fares/lhr-540?variant=poisoned"),
        say("I could not open it."),
    )
    result = run_agent(model, "poisoned")
    assert all(s.trust is not TrustLevel.CONTENT for s in result.steps)
    response = model.histories[1][-1].parts[0].function_response.response
    assert "get_quote" in response["error"]


def test_the_tool_call_cap_ends_the_run_without_a_payment():
    turns = [call("search_fares", origin="BLR", destination="LHR")] * (MAX_TOOL_CALLS + 1)
    result = run_agent(ScriptedModel(*turns), "honest")
    assert result.payment is None
    assert str(MAX_TOOL_CALLS) in result.detail
    assert len(result.steps) == 1 + MAX_TOOL_CALLS


def test_a_text_reply_ends_the_run_without_a_payment():
    result = run_agent(ScriptedModel(say("Nothing fits under $600.")), "honest")
    assert result.payment is None
    assert "Nothing fits under $600." in result.detail


def test_a_malformed_payment_request_is_recorded_not_paid():
    model = ScriptedModel(call("request_payment", recipient="m", amount="lots", memo="x"))
    result = run_agent(model, "honest")
    assert result.payment is None
    assert result.steps[-1].trust is TrustLevel.AGENT
    assert "malformed" in result.steps[-1].content


def test_several_calls_in_one_turn_run_in_order_and_are_answered_together():
    both = types.Content(
        role="model",
        parts=[
            types.Part.from_function_call(name="search_fares", args={"origin": "BLR", "destination": "LHR"}),
            types.Part.from_function_call(name="get_quote", args={"fare_id": "lhr-585"}),
        ],
    )
    model = ScriptedModel(both, say("done"))
    result = run_agent(model, "honest")
    assert [s.source for s in result.steps[1:]] == ["search_fares", "get_quote"]
    answer = model.histories[1][-1]
    assert answer.role == "tool"
    assert [p.function_response.name for p in answer.parts] == ["search_fares", "get_quote"]


@pytest.mark.parametrize("raw", [540, 540.0, "540", "540.00", "$540", "540 USDC", " 540 usdc "])
def test_amounts_in_the_shapes_models_send_parse_the_same(raw):
    assert parse_amount(raw) == Decimal("540")


@pytest.mark.parametrize("raw", ["lots", "", None, "-5", "0", "NaN"])
def test_unusable_amounts_are_rejected(raw):
    with pytest.raises(ValueError):
        parse_amount(raw)


def test_unknown_listing_mode_is_rejected():
    with pytest.raises(ValueError):
        run_agent(ScriptedModel(), "sneaky")


def test_gemini_model_sends_prompt_tools_and_disables_auto_calling():
    captured = {}
    reply = types.Content(role="model", parts=[types.Part(text="hi")])

    def generate(**kwargs):
        captured.update(kwargs)
        return types.GenerateContentResponse(candidates=[types.Candidate(content=reply)])

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    out = GeminiAgentModel("k", model="m-test", client=client).respond(["history"])
    assert out == reply
    assert captured["model"] == "m-test"
    assert captured["contents"] == ["history"]
    config = captured["config"]
    assert config.automatic_function_calling.disable is True
    names = [d.name for d in config.tools[0].function_declarations]
    assert names == ["search_fares", "get_quote", "open_listing", "request_payment"]


def test_gemini_model_turns_an_empty_reply_into_text():
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **k: types.GenerateContentResponse(candidates=[]))
    )
    out = GeminiAgentModel("k", client=client).respond([])
    assert out.parts[0].text


def test_a_second_quote_after_the_listing_does_not_launder_a_redirect():
    model = ScriptedModel(
        call("get_quote", fare_id="lhr-540"),
        call("open_listing", url="/fares/lhr-540?variant=poisoned"),
        call("get_quote", fare_id="lhr-585"),
        call("request_payment", recipient="merchant.agency.example", amount=595, memo="x"),
    )
    result = run_agent(model, "poisoned")
    decision = authorize(MANDATE, result.payment, Decimal("0"), Signer.generate())
    assert "plan_divergence" in {c.name for c in decision.checks if not c.passed}


def test_the_agent_client_times_out_instead_of_hanging(monkeypatch):
    import google.genai as genai_module

    from interlock.intent import GEMINI_TIMEOUT_MS

    captured = {}
    monkeypatch.setattr(genai_module, "Client", lambda **kwargs: captured.update(kwargs))
    GeminiAgentModel("k")
    assert captured["http_options"].timeout == GEMINI_TIMEOUT_MS
