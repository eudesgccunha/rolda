"""Shared test helpers."""

import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
import uvicorn
from fastapi import FastAPI

from api_support import ApiClient
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


ServeApp = Callable[[FastAPI, str | None], ApiClient]


@pytest.fixture
def serve_app() -> Iterator[ServeApp]:
    """Return a function that serves an app and gives a client for it."""
    servers: list[tuple[uvicorn.Server, threading.Thread]] = []

    def serve(app: FastAPI, token: str | None) -> ApiClient:
        config = uvicorn.Config(
            app, host="127.0.0.1", port=0, log_level="warning"
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        port = server.servers[0].sockets[0].getsockname()[1]
        servers.append((server, thread))
        return ApiClient(port, token)

    yield serve
    for server, thread in servers:
        server.should_exit = True
        thread.join(timeout=10)
