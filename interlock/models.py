from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class TrustLevel(str, Enum):
    """Where a step in the agent's instruction chain came from.

    The distinction that matters for authorization is PRINCIPAL and TOOL (things
    the system has reason to trust) versus CONTENT (anything the agent fetched
    from the outside world, which is data and never instruction).
    """

    PRINCIPAL = "principal"
    TOOL = "tool"
    CONTENT = "content"
    AGENT = "agent"


@dataclass(frozen=True)
class PlanHint:
    """Structured payment parameters established by a trusted tool.

    Real tool integrations return structured data, not prose - this is the shape
    the provenance layer compares the final payment against.
    """

    recipient: str
    amount: Decimal


@dataclass(frozen=True)
class InstructionStep:
    source: str
    trust: TrustLevel
    content: str
    plan: PlanHint | None = None


@dataclass(frozen=True)
class Mandate:
    """What the principal actually authorized the agent to do."""

    mandate_id: str
    principal: str
    intent: str
    max_amount: Decimal
    total_budget: Decimal
    allowed_counterparties: tuple[str, ...]
    currency: str
    chain: str


@dataclass(frozen=True)
class PaymentRequest:
    """What the agent is proposing to pay, and the steps that led there."""

    payment_id: str
    mandate_id: str
    recipient: str
    amount: Decimal
    currency: str
    chain: str
    memo: str
    instruction_chain: tuple[InstructionStep, ...]


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str
