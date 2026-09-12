"""Run both demo scenarios against the engine.

Usage: python -m demo.run_attack

No API key, no network, no accounts. That is the point.
"""
import sys

from interlock.engine import authorize
from interlock.trace import Signer

from .scenarios import CLEAN_SCENARIO, INJECTED_SCENARIO

GREEN, RED, DIM, BOLD, RESET = (
    "\033[32m",
    "\033[31m",
    "\033[2m",
    "\033[1m",
    "\033[0m",
)


def render(scenario, decision) -> None:
    verdict = f"{GREEN}ALLOWED{RESET}" if decision.allowed else f"{RED}DENIED{RESET}"
    print(f"\n{BOLD}{scenario.name.upper()}{RESET}  ->  {verdict}")
    print(f"{DIM}{scenario.description}{RESET}\n")

    print(f"{DIM}instruction chain:{RESET}")
    for i, step in enumerate(scenario.payment.instruction_chain):
        flag = f" {RED}<- untrusted{RESET}" if step.trust.value == "content" else ""
        print(f"{DIM}  [{i}] ({step.trust.value}) {step.source}{RESET}{flag}")

    print(f"\n{DIM}checks:{RESET}")
    for check in decision.checks:
        mark = f"{GREEN}pass{RESET}" if check.passed else f"{RED}FAIL{RESET}"
        print(f"  [{mark}] {check.name}: {check.detail}")

    print(f"\n{DIM}ed25519 signature {decision.signature[:32]}...{RESET}")


def main() -> int:
    signer = Signer.generate()
    results = {}
    for scenario in (CLEAN_SCENARIO, INJECTED_SCENARIO):
        decision = authorize(scenario.mandate, scenario.payment, scenario.spent, signer)
        render(scenario, decision)
        results[scenario.name] = decision.allowed

    ok = results["clean"] and not results["injected"]
    status = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(
        f"\n{status}  clean allowed={results['clean']}, "
        f"injected allowed={results['injected']}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
