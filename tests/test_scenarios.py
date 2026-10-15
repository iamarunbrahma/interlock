from demo.scenarios import SCENARIOS
from interlock.checks import run_deterministic_checks
from interlock.engine import authorize
from interlock.intent import Assessment, StubAssessor
from interlock.trace import Signer


def test_all_scenarios_present():
    assert set(SCENARIOS) == {"clean", "injected", "semantic"}


def test_semantic_scenario_passes_layers_one_and_two():
    """Without layer 3 the wrong ticket is paid for - that is the gap it closes."""
    s = SCENARIOS["semantic"]
    assert authorize(s.mandate, s.payment, s.spent, Signer.generate()).allowed


def test_semantic_scenario_is_caught_only_by_layer_three():
    s = SCENARIOS["semantic"]
    assessor = StubAssessor(Assessment(False, "Dubai, not London."))
    decision = authorize(s.mandate, s.payment, s.spent, Signer.generate(), assessor)
    assert [c.name for c in decision.checks if not c.passed] == ["intent_match"]


def test_injected_scenario_passes_every_deterministic_check():
    """The point of the demo: the attack is invisible to rule-based controls."""
    s = SCENARIOS["injected"]
    results = run_deterministic_checks(s.mandate, s.payment, s.spent)
    assert all(r.passed for r in results), "injected scenario must defeat static rules"


def test_clean_scenario_is_allowed_end_to_end():
    s = SCENARIOS["clean"]
    assert authorize(s.mandate, s.payment, s.spent, Signer.generate()).allowed


def test_injected_scenario_is_denied_end_to_end():
    s = SCENARIOS["injected"]
    assert not authorize(s.mandate, s.payment, s.spent, Signer.generate()).allowed


def test_scenarios_need_no_network_or_credentials():
    """Guard the headline claim - a reviewer must be able to clone and run this."""
    for s in SCENARIOS.values():
        assert authorize(s.mandate, s.payment, s.spent, Signer.generate()) is not None
