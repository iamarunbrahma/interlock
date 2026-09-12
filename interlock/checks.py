from decimal import Decimal

from .models import CheckResult, Mandate, PaymentRequest


def run_deterministic_checks(
    mandate: Mandate, payment: PaymentRequest, spent: Decimal
) -> tuple[CheckResult, ...]:
    """Layer 1. Pure comparisons, microseconds, no allocation of consequence."""
    known = payment.recipient in mandate.allowed_counterparties
    within_cap = payment.amount <= mandate.max_amount
    within_budget = (spent + payment.amount) <= mandate.total_budget
    same_rail = payment.currency == mandate.currency and payment.chain == mandate.chain

    return (
        CheckResult(
            "counterparty",
            known,
            f"{payment.recipient} is "
            f"{'on the mandate allowlist' if known else 'NOT on the mandate allowlist'}",
        ),
        CheckResult(
            "amount",
            within_cap,
            f"{payment.amount} {payment.currency} against a per-payment cap "
            f"of {mandate.max_amount}",
        ),
        CheckResult(
            "budget",
            within_budget,
            f"{spent + payment.amount} of {mandate.total_budget} "
            f"{mandate.currency} cumulative",
        ),
        CheckResult(
            "rail",
            same_rail,
            f"{payment.currency} on {payment.chain} against mandate "
            f"{mandate.currency} on {mandate.chain}",
        ),
    )
