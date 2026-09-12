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


def _last_trusted_plan(
    chain: tuple[InstructionStep, ...],
) -> tuple[int, PlanHint] | None:
    for index in range(len(chain) - 1, -1, -1):
        step = chain[index]
        if step.trust is TrustLevel.TOOL and step.plan is not None:
            return index, step.plan
    return None


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


def _check_plan_divergence(payment: PaymentRequest) -> CheckResult:
    found = _last_trusted_plan(payment.instruction_chain)
    if found is None:
        return CheckResult(
            "plan_divergence",
            True,
            "No trusted plan step to compare the payment against",
        )

    index, plan = found
    diverged = payment.recipient != plan.recipient or payment.amount != plan.amount
    intervening = [
        step
        for step in payment.instruction_chain[index + 1 :]
        if step.trust is TrustLevel.CONTENT
    ]

    if not diverged:
        return CheckResult(
            "plan_divergence",
            True,
            f"Payment matches the trusted plan ({plan.recipient}, {plan.amount})",
        )
    if not intervening:
        return CheckResult(
            "plan_divergence",
            True,
            f"Payment differs from the trusted plan ({plan.recipient}, {plan.amount}) "
            "but no untrusted content intervened",
        )

    sources = ", ".join(sorted({step.source for step in intervening}))
    return CheckResult(
        "plan_divergence",
        False,
        f"Payment to {payment.recipient} for {payment.amount} diverges from the "
        f"trusted plan ({plan.recipient}, {plan.amount}) after untrusted content "
        f"from {sources}",
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
