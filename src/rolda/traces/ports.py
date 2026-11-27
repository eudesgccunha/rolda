"""Ports of the traces feature."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from rolda.traces.model import Span


class SpanSource(Protocol):
    """Port that reads normalized spans from a store."""

    async def spans_between(
        self, start: datetime, end: datetime
    ) -> Sequence[Span]:
        """Return spans that started in the half-open window."""
        ...

    async def spans_for_trace(self, trace_id: str) -> Sequence[Span]:
        """Return every span of one trace."""
        ...
