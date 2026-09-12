import dataclasses
from decimal import Decimal

from interlock.checks import run_deterministic_checks
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
    instruction_chain=(InstructionStep("user", TrustLevel.PRINCIPAL, "book it"),),
)


def test_clean_payment_passes_all_four_checks():
    results = run_deterministic_checks(MANDATE, PAYMENT, Decimal("0"))
    assert all(r.passed for r in results)
    assert {r.name for r in results} == {"counterparty", "amount", "budget", "rail"}


def test_unknown_counterparty_fails():
    payment = dataclasses.replace(PAYMENT, recipient="attacker.example")
    results = run_deterministic_checks(MANDATE, payment, Decimal("0"))
    assert [r.name for r in results if not r.passed] == ["counterparty"]


def test_amount_over_cap_fails():
    payment = dataclasses.replace(PAYMENT, amount=Decimal("900"))
    results = run_deterministic_checks(MANDATE, payment, Decimal("0"))
    assert not next(r for r in results if r.name == "amount").passed


def test_amount_exactly_at_cap_passes():
    payment = dataclasses.replace(PAYMENT, amount=Decimal("600"))
    results = run_deterministic_checks(MANDATE, payment, Decimal("0"))
    assert next(r for r in results if r.name == "amount").passed


def test_cumulative_budget_exhausted_fails():
    results = run_deterministic_checks(MANDATE, PAYMENT, Decimal("800"))
    assert not next(r for r in results if r.name == "budget").passed


def test_wrong_chain_fails():
    payment = dataclasses.replace(PAYMENT, chain="ethereum")
    results = run_deterministic_checks(MANDATE, payment, Decimal("0"))
    assert not next(r for r in results if r.name == "rail").passed


def test_wrong_currency_fails():
    payment = dataclasses.replace(PAYMENT, currency="USDT")
    results = run_deterministic_checks(MANDATE, payment, Decimal("0"))
    assert not next(r for r in results if r.name == "rail").passed
