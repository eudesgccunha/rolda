"""Shared test helpers."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from rolda.traces import Operation, Span, SpanStatus

T0 = datetime(2026, 11, 26, 10, tzinfo=UTC)


@pytest.fixture
def make_span() -> Callable[..., Span]:
    """Build a span with sensible defaults; override with keywords."""

    def factory(
        span_id: str,
        *,
        trace_id: str = "t1",
        parent: str | None = None,
        operation: Operation = Operation.OTHER,
        start_s: float = 0,
        duration_ns: int = 1_000_000,
        status: SpanStatus = SpanStatus.OK,
        agent: str | None = "agent-a",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        tool_name: str | None = None,
        tool_arguments: str | None = None,
    ) -> Span:
        return Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent,
            name=span_id,
            agent=agent,
            operation=operation,
            started_at=T0 + timedelta(seconds=start_s),
            duration_ns=duration_ns,
            status=status,
            status_message="boom" if status is SpanStatus.ERROR else "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_name=tool_name,
            tool_arguments=tool_arguments,
        )

    return factory
