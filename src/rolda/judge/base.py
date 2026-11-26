"""Judge port and the default implementation.

Each provider (local model, hosted API) is a strategy implementing
``Judge``, so the detection pipeline never depends on a vendor SDK.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class Verdict(StrEnum):
    """Outcome of judging a finding."""

    FAILURE = "failure"
    FALSE_ALARM = "false_alarm"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class Finding:
    """Suspicious behaviour raised by a deterministic rule."""

    trace_id: str
    rule: str
    evidence: str
    summary: str = ""


@dataclass(frozen=True, slots=True)
class Judgement:
    """Verdict plus the justification shown to a human."""

    verdict: Verdict
    reason: str


class Judge(Protocol):
    """Port implemented by every judge strategy."""

    async def evaluate(self, finding: Finding) -> Judgement:
        """Decide whether a finding is a real failure."""
        ...


class DisabledJudge:
    """Default strategy: no LLM call, a human reviews the finding."""

    async def evaluate(self, finding: Finding) -> Judgement:
        """Return an uncertain verdict for any finding."""
        return Judgement(
            verdict=Verdict.UNCERTAIN,
            reason=f"Judge disabled; review rule '{finding.rule}'.",
        )
