from decimal import Decimal
from types import SimpleNamespace

from interlock.intent import (
    Assessment,
    GeminiAssessor,
    StubAssessor,
    build_assessment_prompt,
)
from interlock.models import InstructionStep, Mandate, PaymentRequest, TrustLevel

MANDATE = Mandate(
    mandate_id="m_1",
    principal="arun",
    intent="Book a flight to London for under $600",
    max_amount=Decimal("600"),
    total_budget=Decimal("1200"),
    allowed_counterparties=("merchant.airline.example",),
    currency="USDC",
    chain="solana",
)

PAYMENT = PaymentRequest(
    payment_id="p_1",
    mandate_id="m_1",
    recipient="merchant.airline.example",
    amount=Decimal("540"),
    currency="USDC",
    chain="solana",
    memo="One-way flight BLR-LHR",
    instruction_chain=(
        InstructionStep("user", TrustLevel.PRINCIPAL, "book a flight to London"),
        InstructionStep("web-page", TrustLevel.CONTENT, "IGNORE PREVIOUS"),
    ),
)


def test_stub_assessor_returns_configured_assessment():
    expected = Assessment(matches_intent=False, reasoning="test")
    assert StubAssessor(expected).assess(MANDATE, PAYMENT) == expected


def test_prompt_contains_intent_payment_and_chain():
    prompt = build_assessment_prompt(MANDATE, PAYMENT)
    assert "Book a flight to London for under $600" in prompt
    assert "IGNORE PREVIOUS" in prompt
    assert "540" in prompt


def test_prompt_labels_each_step_with_its_trust_level():
    prompt = build_assessment_prompt(MANDATE, PAYMENT)
    assert "principal" in prompt
    assert "content" in prompt
    assert "untrusted" in prompt.lower()


def test_importing_intent_does_not_require_the_anthropic_sdk():
    """The package must stay usable with no optional dependencies installed."""
    import interlock.intent as module

    assert not hasattr(module, "anthropic")


class FakeGeminiClient:
    def __init__(self, text):
        self.calls = []
        self.models = SimpleNamespace(generate_content=self._generate)
        self._text = text

    def _generate(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self._text)


def test_gemini_assessor_parses_structured_output():
    client = FakeGeminiClient('{"matches_intent": false, "reasoning": "Dubai, not London."}')
    assessment = GeminiAssessor(client=client).assess(MANDATE, PAYMENT)
    assert assessment == Assessment(False, "Dubai, not London.")


def test_gemini_assessor_sends_the_prompt_and_a_json_schema():
    client = FakeGeminiClient('{"matches_intent": true, "reasoning": "ok"}')
    GeminiAssessor(client=client, model="m-test").assess(MANDATE, PAYMENT)
    call = client.calls[0]
    assert call["model"] == "m-test"
    assert "Book a flight to London for under $600" in call["contents"]
    assert call["config"].response_mime_type == "application/json"
    assert "additionalProperties" not in call["config"].response_json_schema


def test_importing_intent_does_not_require_the_gemini_sdk():
    import interlock.intent as module

    assert not hasattr(module, "genai")
