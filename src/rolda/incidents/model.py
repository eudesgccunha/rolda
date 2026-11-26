"""Incident domain model."""

from dataclasses import dataclass
from datetime import datetime

from rolda.detection import Confidence


@dataclass(frozen=True, slots=True)
class Incident:
    """A stored finding. Unique per ``trace_id`` and ``rule``."""

    trace_id: str
    rule: str
    span_id: str
    evidence: str
    confidence: Confidence
    signature: str
    path: tuple[str, ...]
    detected_at: datetime
