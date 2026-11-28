"""The worker judges whole traces, not the slice that fits in a window."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from rolda.detection import DetectionConfig, default_rules
from rolda.entrypoints.worker import Worker, WorkerConfig
from rolda.incidents import InMemoryIncidentStore
from rolda.traces import InMemorySpanSource, Operation, Span, SpanStatus

SpanFactory = Callable[..., Span]
T0 = datetime(2026, 11, 26, 10, tzinfo=UTC)
LAG = timedelta(minutes=10)


def _worker(
    source: InMemorySpanSource, store: InMemoryIncidentStore
) -> Worker:
    return Worker(
        source=source,
        store=store,
        rules=default_rules(DetectionConfig()),
        config=WorkerConfig(lag=LAG),
        clock=lambda: T0 + timedelta(hours=2),
    )


def _at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def test_a_trace_is_not_judged_before_its_root_arrives(
    make_span: SpanFactory,
) -> None:
    child = make_span(
        "tool",
        parent="root",
        operation=Operation.TOOL,
        start_s=4 * 60,
        status=SpanStatus.ERROR,
    )
    store = InMemoryIncidentStore()
    source = InMemorySpanSource([child])

    result = asyncio.run(_worker(source, store).run_window(_at(0), _at(5)))

    assert result.traces == 0
    assert store.all() == []


def test_the_trace_is_judged_once_the_root_arrives(
    make_span: SpanFactory,
) -> None:
    child = make_span(
        "tool",
        parent="root",
        operation=Operation.TOOL,
        start_s=4 * 60,
        status=SpanStatus.ERROR,
    )
    root = make_span(
        "root", operation=Operation.AGENT, duration_ns=7 * 60 * 10**9
    )
    store = InMemoryIncidentStore()
    source = InMemorySpanSource([child])
    worker = _worker(source, store)

    asyncio.run(worker.run_window(_at(0), _at(5)))
    source.add(root)
    asyncio.run(worker.run_window(_at(5), _at(10)))

    [incident] = store.all()
    assert incident.path == ("root", "tool")


def test_spans_outside_the_window_still_count(make_span: SpanFactory) -> None:
    spans = [
        make_span("root", operation=Operation.AGENT, start_s=0),
        *[
            make_span(
                f"call{i}",
                parent="root",
                operation=Operation.TOOL,
                start_s=60 + i * 60 * 30,
                tool_name="search",
                tool_arguments='{"q": "same"}',
            )
            for i in range(3)
        ],
    ]
    store = InMemoryIncidentStore()
    worker = _worker(InMemorySpanSource(spans), store)

    # Only the last call starts inside this window; the others are much
    # earlier. The loop is visible only if the whole trace is read.
    asyncio.run(worker.run_window(_at(60), _at(65)))

    assert [i.rule for i in store.all()] == ["tool_loop"]


def test_a_trace_whose_root_never_arrives_is_judged_after_the_lag(
    make_span: SpanFactory,
) -> None:
    child = make_span(
        "tool",
        parent="lost-root",
        operation=Operation.TOOL,
        start_s=0,
        status=SpanStatus.ERROR,
    )
    store = InMemoryIncidentStore()
    worker = _worker(InMemorySpanSource([child]), store)

    asyncio.run(worker.run_window(_at(0), _at(5)))
    assert store.all() == []
    asyncio.run(worker.run_window(_at(5), _at(15)))

    assert [i.rule for i in store.all()] == ["span_error"]
