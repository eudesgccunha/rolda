"""The worker builds its baseline from slices, in the background."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from random import Random

from rolda.detection import DetectionConfig, default_rules
from rolda.entrypoints.worker import Worker, WorkerConfig
from rolda.incidents import InMemoryIncidentStore
from rolda.traces import InMemorySpanSource, Operation, Span

SpanFactory = Callable[..., Span]
T0 = datetime(2026, 11, 26, 0, 0, tzinfo=UTC)
SLICE = timedelta(minutes=15)


def _is_slice(start: datetime, end: datetime) -> bool:
    """A baseline slice sits on the 15 minute grid. A window does not."""
    return end - start == SLICE and int(start.timestamp()) % 900 == 0


class _RecordingSource(InMemorySpanSource):
    """Remembers every range that was read."""

    def __init__(self, spans: list[Span]) -> None:
        super().__init__(spans)
        self.reads: list[tuple[datetime, datetime]] = []
        self.window_reads: list[tuple[datetime, datetime]] = []
        self.broken = False

    async def spans_between(
        self, start: datetime, end: datetime
    ) -> list[Span]:
        if _is_slice(start, end):
            if self.broken:
                msg = "database is down"
                raise ConnectionError(msg)
            self.reads.append((start, end))
        else:
            self.window_reads.append((start, end))
        return list(await super().spans_between(start, end))


def _history(make_span: SpanFactory, count: int) -> list[Span]:
    """``count`` healthy traces spread over the day before ``T0 + 1 day``."""
    rng = Random(2)  # noqa: S311 - seeded test data, not crypto
    spans: list[Span] = []
    for i in range(count):
        trace_id = f"h{i}"
        offset = i * 60
        spans.append(
            make_span(
                "root",
                trace_id=trace_id,
                operation=Operation.AGENT,
                start_s=offset,
                duration_ns=rng.randint(40_000_000, 60_000_000),
            )
        )
    return spans


def _worker(source: _RecordingSource, store: InMemoryIncidentStore) -> Worker:
    return Worker(
        source=source,
        store=store,
        rules=default_rules(DetectionConfig()),
        config=WorkerConfig(
            lag=timedelta(minutes=10),
            baseline_span=timedelta(days=1),
            baseline_slice=SLICE,
            baseline_refresh=timedelta(hours=1),
        ),
        clock=lambda: T0 + timedelta(days=1, hours=5),
    )


def _slice_reads(source: _RecordingSource) -> list[tuple[datetime, datetime]]:
    return list(source.reads)


async def _window(worker: Worker, start: datetime) -> None:
    """Run one window and let the background baseline finish."""
    await worker.run_window(start, start + timedelta(minutes=5))
    await worker.wait_for_baseline()


def test_the_history_is_read_in_slices_never_in_one_piece(
    make_span: SpanFactory,
) -> None:
    source = _RecordingSource(_history(make_span, 10))
    worker = _worker(source, InMemoryIncidentStore())

    asyncio.run(_window(worker, T0 + timedelta(days=1)))

    long_reads = [
        r
        for r in source.reads + source.window_reads
        if r[1] - r[0] > SLICE * 2
    ]
    assert long_reads == []
    assert len(_slice_reads(source)) == 96  # one day of 15 minute slices


def test_the_baseline_is_reused_inside_the_refresh_interval(
    make_span: SpanFactory,
) -> None:
    source = _RecordingSource(_history(make_span, 10))
    worker = _worker(source, InMemoryIncidentStore())
    start = T0 + timedelta(days=1)

    async def scenario() -> int:
        await _window(worker, start)
        before = len(_slice_reads(source))
        await _window(worker, start + timedelta(minutes=5))
        return before

    before = asyncio.run(scenario())

    assert len(_slice_reads(source)) == before


def test_a_later_refresh_reads_only_the_new_slices(
    make_span: SpanFactory,
) -> None:
    source = _RecordingSource(_history(make_span, 10))
    worker = _worker(source, InMemoryIncidentStore())
    start = T0 + timedelta(days=1)

    async def scenario() -> int:
        await _window(worker, start)
        first = len(_slice_reads(source))
        await _window(worker, start + timedelta(hours=2))
        return first

    first = asyncio.run(scenario())

    new_reads = len(_slice_reads(source)) - first
    assert 0 < new_reads <= 10  # two hours of new slices, not the whole day


def test_the_first_window_does_not_wait_for_the_baseline(
    make_span: SpanFactory,
) -> None:
    source = _RecordingSource(_history(make_span, 10))
    worker = _worker(source, InMemoryIncidentStore())
    start = T0 + timedelta(days=1)

    async def scenario() -> tuple[int, int]:
        await worker.run_window(start, start + timedelta(minutes=5))
        read_when_it_returned = len(_slice_reads(source))
        await worker.wait_for_baseline()
        return read_when_it_returned, len(_slice_reads(source))

    early, late = asyncio.run(scenario())

    assert early < late == 96


def test_a_failing_history_read_keeps_the_old_baseline_and_retries(
    make_span: SpanFactory,
) -> None:
    source = _RecordingSource(_history(make_span, 10))
    worker = _worker(source, InMemoryIncidentStore())
    start = T0 + timedelta(days=1)
    later = start + timedelta(hours=2)

    async def scenario() -> int:
        await _window(worker, start)
        reads_after_first = len(_slice_reads(source))
        source.broken = True
        await _window(worker, later)
        source.broken = False
        await _window(worker, later + timedelta(minutes=5))
        return reads_after_first

    first = asyncio.run(scenario())

    assert len(_slice_reads(source)) > first  # it tried again after the error
