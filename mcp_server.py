"""Interlock as an MCP server.

Any MCP-capable agent can call `authorize_payment` before it signs a transaction.
No API key required - the decision is computed locally.

Run: python mcp_server.py
"""
import os
from decimal import Decimal

from mcp.server.mcpserver import MCPServer

from interlock.engine import authorize
from interlock.models import (
    InstructionStep,
    Mandate,
    PaymentRequest,
    PlanHint,
    TrustLevel,
)
from interlock.trace import Signer

mcp = MCPServer("interlock")

_signer = (
    Signer.from_hex(os.environ["INTERLOCK_SIGNING_KEY"])
    if os.environ.get("INTERLOCK_SIGNING_KEY")
    else Signer.generate()
)


def _to_step(raw: dict) -> InstructionStep:
    plan = None
    if raw.get("plan_recipient") and raw.get("plan_amount"):
        plan = PlanHint(raw["plan_recipient"], Decimal(str(raw["plan_amount"])))
    return InstructionStep(
        source=raw["source"],
        trust=TrustLevel(raw["trust"]),
        content=raw["content"],
        plan=plan,
    )


@mcp.tool()
def authorize_payment(
    intent: str,
    principal: str,
    max_amount: str,
    total_budget: str,
    allowed_counterparties: list[str],
    currency: str,
    chain: str,
    payment_id: str,
    recipient: str,
    amount: str,
    memo: str,
    instruction_chain: list[dict],
    spent: str = "0",
) -> dict:
    """Decide whether an agent-initiated payment is allowed to settle.

    Call this before signing or broadcasting any transaction.

    Amounts are decimal strings. Each instruction_chain entry is a dict with
    `source`, `trust` (one of principal/tool/content/agent), `content`, and
    optionally `plan_recipient` and `plan_amount` for trusted tool steps that
    established the payment parameters.

    Returns a signed decision with a per-check reasoning trace.
    """
    mandate = Mandate(
        mandate_id=f"mandate_for_{payment_id}",
        principal=principal,
        intent=intent,
        max_amount=Decimal(max_amount),
        total_budget=Decimal(total_budget),
        allowed_counterparties=tuple(allowed_counterparties),
        currency=currency,
        chain=chain,
    )
    payment = PaymentRequest(
        payment_id=payment_id,
        mandate_id=mandate.mandate_id,
        recipient=recipient,
        amount=Decimal(amount),
        currency=currency,
        chain=chain,
        memo=memo,
        instruction_chain=tuple(_to_step(s) for s in instruction_chain),
    )
    return authorize(mandate, payment, Decimal(spent), _signer).to_dict()


if __name__ == "__main__":
    mcp.run()
