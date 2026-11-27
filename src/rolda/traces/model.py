"""Rolda's own trace model, independent of OpenTelemetry attributes."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Operation(StrEnum):
    """What a span did, in Rolda's own vocabulary."""

    AGENT = "agent"
    LLM = "llm"
    TOOL = "tool"
    OTHER = "other"


class SpanStatus(StrEnum):
    """Outcome reported by the span."""

    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


@dataclass(frozen=True, slots=True)
class Span:
    """One unit of work in a trace.

    Prompt and response content is deliberately not part of the model:
    capture is off by default and needs redaction first.
    """

    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    agent: str | None
    operation: Operation
    started_at: datetime
    duration_ns: int
    status: SpanStatus
    status_message: str = ""
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool_name: str | None = None
    tool_arguments: str | None = None


@dataclass(frozen=True, slots=True)
class Trace:
    """All spans that share a trace id, ordered by start time."""

    trace_id: str
    spans: tuple[Span, ...]

    @property
    def root(self) -> Span:
        """Return the earliest span without a parent in this trace."""
        known = {span.span_id for span in self.spans}
        for span in self.spans:
            if span.parent_span_id is None or span.parent_span_id not in known:
                return span
        return self.spans[0]

    def children(self, span_id: str) -> tuple[Span, ...]:
        """Return the direct children of a span, in start order."""
        return tuple(
            span for span in self.spans if span.parent_span_id == span_id
        )


def build_traces(spans: Iterable[Span]) -> list[Trace]:
    """Group spans into traces."""
    grouped: dict[str, list[Span]] = defaultdict(list)
    for span in spans:
        grouped[span.trace_id].append(span)
    return [
        Trace(
            trace_id=trace_id,
            spans=tuple(sorted(items, key=lambda s: s.started_at)),
        )
        for trace_id, items in grouped.items()
    ]
