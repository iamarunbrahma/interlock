from decimal import Decimal

from interlock.models import PlanHint, TrustLevel
from mcp_server import _to_step


def test_plain_step_converts_without_a_plan():
    step = _to_step({"source": "user", "trust": "principal", "content": "book it"})
    assert step.trust is TrustLevel.PRINCIPAL
    assert step.plan is None


def test_tool_step_converts_its_plan_hint():
    step = _to_step(
        {
            "source": "search-tool",
            "trust": "tool",
            "content": "cheapest fare",
            "plan_recipient": "merchant.airline.example",
            "plan_amount": "540",
        }
    )
    assert step.plan == PlanHint("merchant.airline.example", Decimal("540"))


def test_numeric_plan_amount_is_coerced_without_float_error():
    step = _to_step(
        {
            "source": "search-tool",
            "trust": "tool",
            "content": "fare",
            "plan_recipient": "m",
            "plan_amount": 540.55,
        }
    )
    assert step.plan.amount == Decimal("540.55")


def test_untrusted_content_keeps_its_trust_level():
    step = _to_step({"source": "web", "trust": "content", "content": "hostile"})
    assert step.trust is TrustLevel.CONTENT
