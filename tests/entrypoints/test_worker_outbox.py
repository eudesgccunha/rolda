"""The worker with an alert outbox: no alert is lost, none is repeated."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from rolda.alerts import Alert, AlertDeliveryError
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


class _Clock:
    def __init__(self) -> None:
        self.now = T0 + timedelta(hours=1)

    def __call__(self) -> datetime:
        return self.now


class _Channel:
    """An alerter that fails the first ``failures`` times."""

    def __init__(self, name: str, failures: int = 0) -> None:
        self.name = name
        self.alerts: list[Alert] = []
        self._failures = failures

    async def send(self, alert: Alert) -> None:
        self.alerts.append(alert)
        if len(self.alerts) <= self._failures:
            msg = "down"
            raise AlertDeliveryError(msg)


def _spans(make_span: SpanFactory) -> list[Span]:
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


def _worker(
    make_span: SpanFactory,
    store: InMemoryIncidentStore,
    channels: list[_Channel],
    clock: _Clock,
    max_attempts: int = 5,
) -> Worker:
    return Worker(
        source=InMemorySpanSource(_spans(make_span)),
        store=store,
        rules=default_rules(DetectionConfig()),
        config=WorkerConfig(
            alert_max_attempts=max_attempts,
            alert_backoff=timedelta(seconds=30),
        ),
        clock=clock,
        alerters=channels,
        outbox=store,
    )


def test_a_failed_alert_is_retried_in_a_later_window(
    make_span: SpanFactory,
) -> None:
    clock = _Clock()
    flaky = _Channel("slack", failures=1)
    worker = _worker(
        make_span, InMemoryIncidentStore(clock=clock), [flaky], clock
    )

    asyncio.run(worker.run_window(T0, T0 + WINDOW))
    clock.now += timedelta(minutes=1)
    asyncio.run(worker.run_window(T0 + WINDOW, T0 + 2 * WINDOW))

    assert len(flaky.alerts) == 2
    assert "root > tool" in flaky.alerts[1].hypothesis


def test_only_the_failing_channel_is_retried(make_span: SpanFactory) -> None:
    clock = _Clock()
    good = _Channel("teams")
    flaky = _Channel("slack", failures=1)
    worker = _worker(
        make_span, InMemoryIncidentStore(clock=clock), [good, flaky], clock
    )

    asyncio.run(worker.run_window(T0, T0 + WINDOW))
    clock.now += timedelta(minutes=1)
    asyncio.run(worker.run_window(T0 + WINDOW, T0 + 2 * WINDOW))

    assert len(good.alerts) == 1
    assert len(flaky.alerts) == 2


def test_a_channel_that_never_works_stops_after_the_maximum(
    make_span: SpanFactory,
) -> None:
    clock = _Clock()
    broken = _Channel("slack", failures=1000)
    worker = _worker(
        make_span,
        InMemoryIncidentStore(clock=clock),
        [broken],
        clock,
        max_attempts=3,
    )

    for _ in range(8):
        asyncio.run(worker.run_window(T0, T0 + WINDOW))
        clock.now += timedelta(hours=1)

    assert len(broken.alerts) == 3


def test_a_delivered_alert_is_never_sent_again(make_span: SpanFactory) -> None:
    clock = _Clock()
    channel = _Channel("slack")
    worker = _worker(
        make_span, InMemoryIncidentStore(clock=clock), [channel], clock
    )

    for _ in range(3):
        asyncio.run(worker.run_window(T0, T0 + WINDOW))
        clock.now += timedelta(hours=1)

    assert len(channel.alerts) == 1


def test_a_channel_removed_from_the_configuration_is_dropped(
    make_span: SpanFactory,
) -> None:
    clock = _Clock()
    store = InMemoryIncidentStore(clock=clock)
    old = _worker(make_span, store, [_Channel("slack", failures=1000)], clock)
    asyncio.run(old.run_window(T0, T0 + WINDOW))
    replacement = _worker(
        make_span, store, [_Channel("teams")], clock, max_attempts=2
    )

    for _ in range(4):
        clock.now += timedelta(hours=1)
        asyncio.run(replacement.run_window(T0 + WINDOW, T0 + 2 * WINDOW))

    pending = asyncio.run(
        store.pending(limit=10, max_attempts=2, backoff=timedelta(seconds=1))
    )
    assert [d.channel for d in pending] == []
