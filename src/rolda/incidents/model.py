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


OrderKey = tuple[datetime, str, str]


def order_key(incident: Incident) -> OrderKey:
    """Return the sort key that lists incidents newest first.

    It is also the paging cursor: ties on time are broken by trace and rule,
    so a page never skips or repeats an incident.
    """
    return (incident.detected_at, incident.trace_id, incident.rule)


def agent_of(incident: Incident) -> str:
    """Return the agent name stored first in the signature."""
    return incident.signature.split("|", 1)[0]
