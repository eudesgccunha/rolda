"""Detection domain model."""

from dataclasses import dataclass
from enum import StrEnum


class Confidence(StrEnum):
    """How sure a rule is about a finding."""

    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class Finding:
    """Suspicious behaviour raised by a deterministic rule."""

    trace_id: str
    rule: str
    span_id: str
    evidence: str
    confidence: Confidence = Confidence.HIGH
