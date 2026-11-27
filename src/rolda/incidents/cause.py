"""Probable cause of an incident (SPEC section 5).

The result is a hypothesis shown with its evidence, not a conclusion.
"""

import re
from dataclasses import dataclass

from rolda.detection import Finding
from rolda.traces import SpanStatus, Trace

_MAX_ERROR = 80
_HEX_ID = re.compile(r"\b[0-9a-f]{8,}\b")
_NUMBER = re.compile(r"\d+")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ProbableCause:
    """Where a finding probably started and how to group it."""

    signature: str
    path: tuple[str, ...]
    hypothesis: str


def normalize_error(message: str) -> str:
    """Make error messages comparable: no ids, numbers or separators."""
    text = message.lower().replace("|", " ")
    text = _HEX_ID.sub("<id>", text)
    text = _NUMBER.sub("<n>", text)
    return _SPACES.sub(" ", text).strip()[:_MAX_ERROR]


def _path_to(trace: Trace, span_id: str) -> tuple[str, ...]:
    by_id = {span.span_id: span for span in trace.spans}
    names: list[str] = []
    seen: set[str] = set()
    current = by_id.get(span_id)
    while current is not None and current.span_id not in seen:
        seen.add(current.span_id)
        names.append(current.name)
        parent = current.parent_span_id
        current = by_id.get(parent) if parent else None
    return tuple(reversed(names))


def hypothesis_for(rule: str, path: tuple[str, ...], evidence: str) -> str:
    """Write the hypothesis shown with an incident."""
    where = " > ".join(path) if path else "unknown span"
    return f"{rule} at {where}: {evidence}"


def probable_cause(trace: Trace, finding: Finding) -> ProbableCause:
    """Build the path from the root to the span behind a finding."""
    path = _path_to(trace, finding.span_id)
    span = next((s for s in trace.spans if s.span_id == finding.span_id), None)
    if span is None:
        agent = trace.root.agent or "unknown"
        operation, error = "other", ""
    else:
        agent = trace.root.agent or span.agent or "unknown"
        operation = span.operation.value
        error = (
            normalize_error(span.status_message)
            if span.status is SpanStatus.ERROR
            else ""
        )
    agent = agent.replace("|", "_")
    signature = "|".join([agent, finding.rule, operation, error])
    hypothesis = hypothesis_for(finding.rule, path, finding.evidence)
    return ProbableCause(signature=signature, path=path, hypothesis=hypothesis)
