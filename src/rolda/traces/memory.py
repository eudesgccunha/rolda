"""In-memory ``SpanSource`` for tests and local runs."""

from collections.abc import Iterable, Sequence
from datetime import datetime

from rolda.traces.model import Span


class InMemorySpanSource:
    """Serve spans from a list, filtered by start time."""

    def __init__(self, spans: Iterable[Span] = ()) -> None:
        self._spans = list(spans)

    def add(self, span: Span) -> None:
        """Add a span, as if it arrived late."""
        self._spans.append(span)

    async def spans_between(
        self, start: datetime, end: datetime
    ) -> Sequence[Span]:
        """Return spans that started in ``[start, end)``."""
        return [s for s in self._spans if start <= s.started_at < end]

    async def spans_for_trace(self, trace_id: str) -> Sequence[Span]:
        """Return every span of one trace."""
        return [s for s in self._spans if s.trace_id == trace_id]

    async def spans_for_traces(
        self, trace_ids: Sequence[str]
    ) -> Sequence[Span]:
        """Return every span of each of the given traces."""
        wanted = set(trace_ids)
        return [s for s in self._spans if s.trace_id in wanted]
