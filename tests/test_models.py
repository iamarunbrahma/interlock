import dataclasses
from decimal import Decimal

import pytest

from interlock.models import (
    CheckResult,
    InstructionStep,
    Mandate,
    PaymentRequest,
    PlanHint,
    TrustLevel,
)


def test_trust_levels_are_the_four_we_model():
    assert {t.value for t in TrustLevel} == {"principal", "tool", "content", "agent"}


def test_instruction_step_defaults_to_no_plan_hint():
    step = InstructionStep("user", TrustLevel.PRINCIPAL, "book a flight")
    assert step.plan is None


def test_tool_step_can_carry_a_structured_plan():
    hint = PlanHint("merchant.airline.example", Decimal("540"))
    step = InstructionStep("search-tool", TrustLevel.TOOL, "3 fares found", hint)
    assert step.plan.amount == Decimal("540")


def test_models_are_frozen():
    step = InstructionStep("user", TrustLevel.PRINCIPAL, "x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        step.content = "y"


def test_check_result_carries_a_human_readable_detail():
    assert CheckResult("amount", True, "within cap").detail == "within cap"


def test_payment_request_holds_typed_steps():
    payment = PaymentRequest(
        payment_id="p_1",
        mandate_id="m_1",
        recipient="merchant.airline.example",
        amount=Decimal("540"),
        currency="USDC",
        chain="solana",
        memo="flight",
        instruction_chain=(InstructionStep("user", TrustLevel.PRINCIPAL, "book it"),),
    )
    assert payment.instruction_chain[0].trust is TrustLevel.PRINCIPAL


def test_mandate_holds_allowlist_as_a_tuple():
    mandate = Mandate(
        mandate_id="m_1",
        principal="arun",
        intent="book a flight",
        max_amount=Decimal("600"),
        total_budget=Decimal("1200"),
        allowed_counterparties=("merchant.airline.example",),
        currency="USDC",
        chain="solana",
    )
    assert mandate.allowed_counterparties == ("merchant.airline.example",)
