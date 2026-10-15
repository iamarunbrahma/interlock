"""Layer 2 - information-flow analysis over the agent's instruction chain.

The question this layer answers is not "is this payment sensible" but "did
anything untrusted get between the plan and the payment". That is a structural
question, so it is answered structurally: no model, no network, no secrets.
"""

from .models import CheckResult, InstructionStep, PaymentRequest, PlanHint, TrustLevel

OVERRIDE_PATTERNS: tuple[str, ...] = (
    "ignore previous",
    "ignore all previous",
    "ignore the above",
    "disregard previous",
    "disregard the above",
    "forget the above",
    "new instructions",
    "instead send",
    "instead pay",
    "override",
    "system:",
)

CONCEALMENT_PATTERNS: tuple[str, ...] = (
    "do not mention",
    "don't mention",
    "do not disclose",
    "do not tell",
    "do not report",
    "without informing",
    "silently",
)


def _untrusted_hits(
    chain: tuple[InstructionStep, ...], patterns: tuple[str, ...]
) -> list[tuple[str, str]]:
    """Pattern hits in untrusted steps only. Trusted sources are allowed to be bossy."""
    return [
        (step.source, pattern)
        for step in chain
        if step.trust is TrustLevel.CONTENT
        for pattern in patterns
        if pattern in step.content.lower()
    ]


def _trusted_plans(chain: tuple[InstructionStep, ...]) -> list[tuple[int, PlanHint]]:
    return [
        (index, step.plan)
        for index, step in enumerate(chain)
        if step.trust is TrustLevel.TOOL and step.plan is not None
    ]


def _check_patterns(
    chain: tuple[InstructionStep, ...],
    patterns: tuple[str, ...],
    name: str,
    clean_detail: str,
) -> CheckResult:
    hits = _untrusted_hits(chain, patterns)
    if not hits:
        return CheckResult(name, True, clean_detail)
    rendered = ", ".join(f'"{pattern}" in {source}' for source, pattern in hits)
    return CheckResult(name, False, f"Untrusted content contains {rendered}")


def _terms(plan: PlanHint) -> str:
    return f"({plan.recipient}, {plan.amount})"


def _check_plan_divergence(payment: PaymentRequest) -> CheckResult:
    chain = payment.instruction_chain
    plans = _trusted_plans(chain)
    if not plans:
        return CheckResult(
            "plan_divergence",
            True,
            "No trusted plan step to compare the payment against",
        )

    def matches(plan: PlanHint) -> bool:
        return payment.recipient == plan.recipient and payment.amount == plan.amount

    intervening_at = [
        index
        for index in range(plans[0][0] + 1, len(chain))
        if chain[index].trust is TrustLevel.CONTENT
    ]
    if not intervening_at:
        latest = plans[-1][1]
        if matches(latest):
            return CheckResult(
                "plan_divergence", True, f"Payment matches the trusted plan {_terms(latest)}"
            )
        return CheckResult(
            "plan_divergence",
            True,
            f"Payment differs from the trusted plan {_terms(latest)} "
            "but no untrusted content intervened",
        )

    # Untrusted content that follows a trusted plan can steer everything after it,
    # including the agent's choice to quote again. So the payment must match one of
    # the plans made before that content - an agent comparing several trusted quotes
    # may pay any of them; a quote taken after the content does not count.
    anchors = [plan for index, plan in plans if index < intervening_at[0]]
    matched = next((plan for plan in anchors if matches(plan)), None)
    if matched is not None:
        return CheckResult(
            "plan_divergence",
            True,
            f"Payment matches the trusted plan {_terms(matched)}, made before any "
            "untrusted content",
        )

    sources = ", ".join(sorted({chain[index].source for index in intervening_at}))
    expected = "; ".join(_terms(plan) for plan in anchors)
    return CheckResult(
        "plan_divergence",
        False,
        f"Payment to {payment.recipient} for {payment.amount} diverges from the "
        f"trusted plan {expected} after untrusted content from {sources}",
    )


def run_provenance_checks(payment: PaymentRequest) -> tuple[CheckResult, ...]:
    chain = payment.instruction_chain
    return (
        _check_patterns(
            chain,
            OVERRIDE_PATTERNS,
            "override_language",
            "No imperative override language in untrusted content",
        ),
        _check_plan_divergence(payment),
        _check_patterns(
            chain,
            CONCEALMENT_PATTERNS,
            "concealment",
            "No concealment instruction in untrusted content",
        ),
    )
