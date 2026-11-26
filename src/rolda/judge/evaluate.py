"""Measure how well a judge agrees with human labels."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from rolda.evals import EvalCase
from rolda.judge.base import Finding, Judge, Verdict
from rolda.judge.kappa import cohen_kappa

DEFAULT_MIN_CASES = 30


class InsufficientCasesError(ValueError):
    """Raised when there are too few labeled cases to measure kappa."""


@dataclass(frozen=True, slots=True)
class JudgeReport:
    """Agreement between a judge and human labels."""

    kappa: float
    agreement: float
    scored: int
    uncertain: int
    confusion: dict[tuple[str, str], int]


def summarize(case: EvalCase) -> str:
    """Describe a case's behavior for the judge. Never include the label."""
    lines = [f"rule: {case.rule}", f"signature: {case.signature}", "spans:"]
    lines.extend(
        f"- {span.name} ({span.operation}) status={span.status} "
        f"tool={span.tool or '-'} "
        f"tokens={span.input_tokens}/{span.output_tokens} "
        f"duration_ms={span.duration_ns / 1_000_000:.1f} "
        f"parent={span.parent_span_id or '-'}"
        for span in case.spans
    )
    return "\n".join(lines)


async def evaluate_judge(
    judge: Judge,
    cases: Sequence[EvalCase],
    *,
    min_cases: int = DEFAULT_MIN_CASES,
) -> JudgeReport:
    """Run the judge on every case and compare it with the human label.

    Uncertain verdicts are counted apart and left out of kappa.
    """
    if len(cases) < min_cases:
        msg = f"need at least {min_cases} labeled cases, got {len(cases)}"
        raise InsufficientCasesError(msg)
    human: list[str] = []
    machine: list[str] = []
    uncertain = 0
    for case in cases:
        judgement = await judge.evaluate(
            Finding(
                trace_id=case.trace_id,
                rule=case.rule,
                evidence=case.signature,
                summary=summarize(case),
            )
        )
        if judgement.verdict is Verdict.UNCERTAIN:
            uncertain += 1
            continue
        human.append(case.label)
        machine.append(judgement.verdict.value)
    if not human:
        msg = "the judge answered uncertain for every case"
        raise InsufficientCasesError(msg)
    agreed = sum(a == b for a, b in zip(human, machine, strict=True))
    return JudgeReport(
        kappa=cohen_kappa(human, machine),
        agreement=agreed / len(human),
        scored=len(human),
        uncertain=uncertain,
        confusion=dict(Counter(zip(human, machine, strict=True))),
    )
