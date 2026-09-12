import json

import pytest

from app import decide


@pytest.mark.parametrize("name,expected", [("clean", True), ("injected", False)])
def test_decide_returns_the_expected_verdict(name, expected):
    assert decide(name)["allowed"] is expected


def test_decide_payload_is_json_serialisable():
    assert json.loads(json.dumps(decide("injected")))["allowed"] is False


def test_decide_exposes_the_typed_instruction_chain():
    chain = decide("injected")["scenario"]["instruction_chain"]
    assert [s["trust"] for s in chain] == ["principal", "tool", "content", "agent"]


def test_decide_rejects_an_unknown_scenario():
    with pytest.raises(KeyError):
        decide("nope")
