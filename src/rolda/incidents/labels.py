"""Labels: what a human or the judge decided about an incident."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from rolda.judge import Verdict


class LabelSource(StrEnum):
    """Who produced a label. Kept apart to measure agreement later."""

    HUMAN = "human"
    JUDGE = "judge"


@dataclass(frozen=True, slots=True)
class Label:
    """A verdict on one incident. Unique per incident and source."""

    trace_id: str
    rule: str
    source: LabelSource
    verdict: Verdict
    reason: str
    labeler: str
    labeled_at: datetime
