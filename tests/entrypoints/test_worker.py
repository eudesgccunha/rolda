"""Tests for the worker window processing."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from rolda.detection import DetectionConfig, default_rules
from rolda.entrypoints.worker import Worker, WorkerConfig
from rolda.incidents import InMemoryIncidentStore
from rolda.traces import (
    InMemorySpanSource,
    Operation,
    Span,
    SpanStatus,
)

SpanFactory = Callable[..., Span]
T0 = datetime(2026, 11, 26, 10, tzinfo=UTC)
WINDOW = timedelta(minutes=5)
NOW = T0 + timedelta(hours=1)


def _worker(spans: list[Span], store: InMemoryIncidentStore) -> Worker:
    return Worker(
        source=InMemorySpanSource(spans),
        store=store,
        rules=default_rules(DetectionConfig()),
        config=WorkerConfig(lag=timedelta(minutes=2)),
        clock=lambda: NOW,
    )


def _failing_trace(make_span: SpanFactory) -> list[Span]:
    return [
        make_span("root", operation=Operation.AGENT),
        make_span(
            "tool",
            parent="root",
            operation=Operation.TOOL,
            start_s=1,
            status=SpanStatus.ERROR,
        ),
    ]


def test_window_creates_an_incident_for_a_failing_trace(
    make_span: SpanFactory,
) -> None:
    store = InMemoryIncidentStore()
    worker = _worker(_failing_trace(make_span), store)

    result = asyncio.run(worker.run_window(T0, T0 + WINDOW))

    assert result.new_incidents == 1
    [incident] = store.all()
    assert incident.rule == "span_error"
    assert incident.span_id == "tool"
    assert incident.detected_at == NOW


def test_reprocessing_the_same_window_does_not_duplicate(
    make_span: SpanFactory,
) -> None:
    store = InMemoryIncidentStore()
    worker = _worker(_failing_trace(make_span), store)

    first = asyncio.run(worker.run_window(T0, T0 + WINDOW))
    second = asyncio.run(worker.run_window(T0, T0 + WINDOW))

    assert (first.new_incidents, second.new_incidents) == (1, 0)
    assert second.findings == 1
    assert len(store.all()) == 1


def test_late_span_inside_lag_is_seen_by_the_next_window(
    make_span: SpanFactory,
) -> None:
    spans = [
        make_span("root", operation=Operation.AGENT, start_s=290),
        make_span(
            "tool",
            parent="root",
            operation=Operation.TOOL,
            start_s=295,
            status=SpanStatus.ERROR,
        ),
    ]
    store = InMemoryIncidentStore()
    source = InMemorySpanSource(spans[:1])
    worker = Worker(
        source=source,
        store=store,
        rules=default_rules(DetectionConfig()),
        config=WorkerConfig(lag=timedelta(minutes=2)),
        clock=lambda: NOW,
    )

    asyncio.run(worker.run_window(T0, T0 + WINDOW))
    source.add(spans[1])
    asyncio.run(worker.run_window(T0 + WINDOW, T0 + 2 * WINDOW))
    asyncio.run(worker.run_window(T0 + WINDOW, T0 + 2 * WINDOW))

    assert [i.span_id for i in store.all()] == ["tool"]


def test_healthy_window_creates_no_incident(
    make_span: SpanFactory,
) -> None:
    store = InMemoryIncidentStore()
    worker = _worker([make_span("root", operation=Operation.AGENT)], store)

    result = asyncio.run(worker.run_window(T0, T0 + WINDOW))

    assert result.traces == 1
    assert result.new_incidents == 0


def test_incident_carries_the_probable_cause(
    make_span: SpanFactory,
) -> None:
    store = InMemoryIncidentStore()
    worker = _worker(_failing_trace(make_span), store)

    asyncio.run(worker.run_window(T0, T0 + WINDOW))

    [incident] = store.all()
    assert incident.path == ("root", "tool")
    assert incident.signature == "agent-a|span_error|tool|boom"
