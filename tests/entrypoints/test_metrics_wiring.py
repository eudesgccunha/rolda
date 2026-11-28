"""The worker loop and the alert sender report what they do."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from rolda.alerts import Alert, AlertDeliveryError
from rolda.detection import DetectionConfig, default_rules
from rolda.entrypoints.settings import load_settings
from rolda.entrypoints.worker import (
    WindowResult,
    Worker,
    WorkerConfig,
    register_worker_metrics,
    serve,
)
from rolda.incidents import InMemoryIncidentStore
from rolda.observability import Metrics
from rolda.traces import InMemorySpanSource, Operation, Span, SpanStatus

ENV = {
    "CLICKHOUSE_USER": "u",
    "CLICKHOUSE_PASSWORD": "p",
    "POSTGRES_USER": "pu",
    "POSTGRES_PASSWORD": "pp",
}
SpanFactory = Callable[..., Span]
T = datetime(2026, 11, 26, 10, 0, tzinfo=UTC)


def _at(minutes: float) -> datetime:
    return T + timedelta(minutes=minutes)


class _Worker:
    def __init__(self, fail_first: bool = False) -> None:
        self._fail_first = fail_first
        self.calls = 0

    async def run_window(self, start: datetime, end: datetime) -> WindowResult:
        self.calls += 1
        if self._fail_first and self.calls == 1:
            msg = "down"
            raise ConnectionError(msg)
        return WindowResult(traces=3, findings=2, new_incidents=2)


class _Clock:
    """A clock that moves one minute each time the loop sleeps."""

    def __init__(self, start_minute: float) -> None:
        self.now = _at(start_minute)

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        del seconds
        self.now += timedelta(minutes=1)


def _metrics() -> Metrics:
    metrics = Metrics()
    register_worker_metrics(metrics)
    return metrics


def test_windows_incidents_cursor_and_lag_are_reported() -> None:
    metrics = _metrics()
    clock = _Clock(5)

    asyncio.run(
        serve(
            _Worker(fail_first=True),
            load_settings(ENV),
            clock=clock,
            sleep=clock.sleep,
            iterations=3,
            metrics=metrics,
        )
    )

    text = metrics.render()
    assert 'rolda_worker_windows_total{result="ok"} 2' in text
    assert 'rolda_worker_windows_total{result="error"} 1' in text
    assert "rolda_worker_incidents_total 4" in text
    assert (
        f"rolda_worker_cursor_timestamp_seconds {int(_at(7).timestamp())}"
        in text
    )
    assert "rolda_worker_lag_seconds 0" in text
    assert "rolda_worker_is_leader 1" in text
    assert metrics.last_iteration == _at(7)


class _Standby:
    async def try_acquire(self, name: str) -> bool:
        del name
        return False

    async def is_held(self) -> bool:
        return False

    async def release(self) -> None:
        return None


def test_a_standby_worker_reports_that_it_is_not_the_leader() -> None:
    metrics = _metrics()
    clock = _Clock(5)

    asyncio.run(
        serve(
            _Worker(),
            load_settings(ENV),
            clock=clock,
            sleep=clock.sleep,
            iterations=2,
            leadership=_Standby(),
            metrics=metrics,
        )
    )

    assert "rolda_worker_is_leader 0" in metrics.render()
    assert metrics.last_iteration is not None


class _Channel:
    name = "slack"

    def __init__(self, fail: bool) -> None:
        self._fail = fail

    async def send(self, alert: Alert) -> None:
        del alert
        if self._fail:
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


def test_alert_results_are_counted_per_channel(
    make_span: SpanFactory,
) -> None:
    for fail, result in ((False, "ok"), (True, "error")):
        metrics = _metrics()
        store = InMemoryIncidentStore()
        worker = Worker(
            source=InMemorySpanSource(_spans(make_span)),
            store=store,
            rules=default_rules(DetectionConfig()),
            config=WorkerConfig(),
            clock=lambda: _at(60),
            alerters=[_Channel(fail)],
            outbox=store,
            metrics=metrics,
        )

        asyncio.run(worker.run_window(_at(0), _at(5)))

        text = metrics.render()
        assert (
            f'rolda_worker_alerts_total{{channel="slack",result="{result}"}} 1'
            in text
        )


def test_window_and_baseline_durations_are_reported(
    make_span: SpanFactory,
) -> None:
    metrics = _metrics()
    store = InMemoryIncidentStore()
    worker = Worker(
        source=InMemorySpanSource(_spans(make_span)),
        store=store,
        rules=default_rules(DetectionConfig()),
        config=WorkerConfig(),
        clock=lambda: _at(60),
        metrics=metrics,
    )

    async def scenario() -> None:
        await worker.run_window(_at(0), _at(5))
        await worker.wait_for_baseline()

    asyncio.run(scenario())

    text = metrics.render()
    assert "rolda_worker_baseline_build_seconds " in text
    assert "rolda_worker_baseline_traces " in text
    assert "rolda_worker_window_duration_seconds " in text
