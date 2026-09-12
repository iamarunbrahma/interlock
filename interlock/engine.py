from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from .checks import run_deterministic_checks
from .intent import Assessor
from .models import CheckResult, Mandate, PaymentRequest
from .provenance import run_provenance_checks
from .trace import Signer, canonical_payload


@dataclass(frozen=True)
class Decision:
    payment_id: str
    allowed: bool
    checks: tuple[CheckResult, ...]
    issued_at: str
    signature: str
    public_key: str

    def to_dict(self) -> dict:
        return {
            "payment_id": self.payment_id,
            "allowed": self.allowed,
            "issued_at": self.issued_at,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in self.checks
            ],
            "signature": self.signature,
            "public_key": self.public_key,
        }


def authorize(
    mandate: Mandate,
    payment: PaymentRequest,
    spent: Decimal,
    signer: Signer,
    assessor: Assessor | None = None,
) -> Decision:
    """Decide whether a payment may settle.

    Layers run cheapest-first and short-circuit. A decision has to be cheap enough
    to price per decision, so the expensive layers only see what the cheap ones
    could not settle.
    """
    checks = run_deterministic_checks(mandate, payment, spent)

    if all(c.passed for c in checks):
        checks = checks + run_provenance_checks(payment)

    if all(c.passed for c in checks) and assessor is not None:
        assessment = assessor.assess(mandate, payment)
        checks = checks + (
            CheckResult("intent_match", assessment.matches_intent, assessment.reasoning),
        )

    allowed = all(c.passed for c in checks)
    issued_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = canonical_payload(payment.payment_id, allowed, checks, issued_at)

    return Decision(
        payment_id=payment.payment_id,
        allowed=allowed,
        checks=checks,
        issued_at=issued_at,
        signature=signer.sign(payload),
        public_key=signer.public_key_hex,
    )
