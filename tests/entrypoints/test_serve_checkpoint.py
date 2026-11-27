"""The worker loop with a checkpoint, a leader lock and a stop signal."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import pytest

from rolda.checkpoints import (
    CheckpointStore,
    InMemoryCheckpointStore,
    Leadership,
)
from rolda.entrypoints.settings import Settings, load_settings
from rolda.entrypoints.worker import WindowResult, serve

ENV = {
    "CLICKHOUSE_USER": "u",
    "CLICKHOUSE_PASSWORD": "p",
    "POSTGRES_USER": "pu",
    "POSTGRES_PASSWORD": "pp",
}
T = datetime(2026, 11, 26, 10, 0, tzinfo=UTC)


def _at(minutes: float) -> datetime:
    return T + timedelta(minutes=minutes)


def _settings(**extra: str) -> Settings:
    return load_settings({**ENV, **extra})


class _Worker:
    def __init__(self, fail_on: set[int] | None = None) -> None:
        self.windows: list[tuple[datetime, datetime]] = []
        self._fail_on = fail_on or set()

    async def run_window(self, start: datetime, end: datetime) -> WindowResult:
        self.windows.append((start, end))
        if len(self.windows) in self._fail_on:
            msg = "database is down"
            raise ConnectionError(msg)
        return WindowResult(traces=0, findings=0, new_incidents=0)


class _Clock:
    def __init__(self, *minutes: float) -> None:
        self._values = iter(_at(m) for m in minutes)

    def __call__(self) -> datetime:
        return next(self._values)


async def _no_sleep(seconds: float) -> None:
    del seconds


def _run(
    worker: _Worker,
    clock: _Clock,
    iterations: int,
    *,
    settings: Settings | None = None,
    checkpoints: CheckpointStore | None = None,
    leadership: Leadership | None = None,
) -> None:
    asyncio.run(
        serve(
            worker,
            settings or _settings(),
            clock=clock,
            sleep=_no_sleep,
            iterations=iterations,
            checkpoints=checkpoints,
            leadership=leadership,
        )
    )


def test_the_first_window_starts_at_the_saved_checkpoint() -> None:
    store = InMemoryCheckpointStore()
    asyncio.run(store.set("worker", _at(0)))
    worker = _Worker()

    _run(worker, _Clock(3), 1, checkpoints=store)

    assert worker.windows == [(_at(0), _at(3))]


def test_the_checkpoint_moves_forward_after_each_window() -> None:
    store = InMemoryCheckpointStore()
    worker = _Worker()

    _run(worker, _Clock(5, 6), 2, checkpoints=store)

    assert asyncio.run(store.get("worker")) == _at(6)


def test_a_failed_window_does_not_move_the_checkpoint() -> None:
    store = InMemoryCheckpointStore()
    asyncio.run(store.set("worker", _at(0)))
    worker = _Worker(fail_on={1})

    _run(worker, _Clock(3, 4), 2, checkpoints=store)

    first, retry = worker.windows
    assert retry[0] == first[0] == _at(0)
    assert asyncio.run(store.get("worker")) == _at(4)


def test_a_checkpoint_error_counts_as_a_failure() -> None:
    class Broken(InMemoryCheckpointStore):
        calls = 0

        async def set(self, name: str, value: datetime) -> None:
            type(self).calls += 1
            if type(self).calls == 1:
                msg = "cannot write"
                raise ConnectionError(msg)
            await super().set(name, value)

    store = Broken()
    worker = _Worker()

    _run(worker, _Clock(5, 6), 2, checkpoints=store)

    first, retry = worker.windows
    assert retry[0] == first[0]
    assert asyncio.run(store.get("worker")) == _at(6)


def test_a_long_outage_is_capped_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = InMemoryCheckpointStore()
    asyncio.run(store.set("worker", _at(-60 * 24 * 5)))
    worker = _Worker()

    with caplog.at_level(logging.WARNING):
        _run(
            worker,
            _Clock(0),
            1,
            checkpoints=store,
            settings=_settings(ROLDA_MAX_CATCHUP_SECONDS="3600"),
        )

    assert worker.windows[0][0] == _at(-60)
    assert "skipping" in caplog.text


def test_catching_up_runs_in_chunks_without_sleeping() -> None:
    store = InMemoryCheckpointStore()
    asyncio.run(store.set("worker", _at(-30)))
    worker = _Worker()
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    asyncio.run(
        serve(
            worker,
            _settings(ROLDA_CHUNK_SECONDS="600"),
            clock=_Clock(0, 0, 0, 0, 0),
            sleep=record_sleep,
            iterations=3,
            checkpoints=store,
        )
    )

    assert worker.windows == [
        (_at(-30), _at(-20)),
        (_at(-20), _at(-10)),
        (_at(-10), _at(0)),
    ]
    assert sleeps == [60.0]


class _Leadership:
    def __init__(self, grants: list[bool]) -> None:
        self._grants = iter(grants)
        self.held = False
        self.released = 0
        self.acquisitions = 0

    async def try_acquire(self, name: str) -> bool:
        del name
        self.acquisitions += 1
        self.held = next(self._grants)
        return self.held

    async def is_held(self) -> bool:
        return self.held

    async def release(self) -> None:
        self.released += 1
        self.held = False


def test_a_standby_worker_processes_nothing_until_it_leads() -> None:
    leadership = _Leadership([False, False, True])
    worker = _Worker()

    _run(worker, _Clock(5, 6, 7), 3, leadership=leadership)

    assert len(worker.windows) == 1
    assert leadership.released == 1


def test_losing_the_lock_stops_the_work_and_reacquires() -> None:
    leadership = _Leadership([True, False, True])
    worker = _Worker()

    async def lose_the_lock(seconds: float) -> None:
        del seconds
        leadership.held = False

    asyncio.run(
        serve(
            worker,
            _settings(),
            clock=_Clock(5, 6, 7),
            sleep=lose_the_lock,
            iterations=3,
            leadership=leadership,
        )
    )

    assert len(worker.windows) == 2
    assert leadership.acquisitions == 3


def test_a_new_leader_resumes_from_the_shared_checkpoint() -> None:
    store = InMemoryCheckpointStore()
    asyncio.run(store.set("worker", _at(0)))
    leadership = _Leadership([False, True])
    worker = _Worker()

    _run(worker, _Clock(5, 6), 2, checkpoints=store, leadership=leadership)

    assert worker.windows == [(_at(0), _at(5))]


def test_the_stop_event_ends_the_loop_and_releases_the_lock() -> None:
    leadership = _Leadership([True])
    stop = asyncio.Event()
    worker = _Worker()

    async def stopping_sleep(seconds: float) -> None:
        del seconds
        stop.set()

    asyncio.run(
        serve(
            worker,
            _settings(),
            clock=_Clock(5, 6, 7),
            sleep=stopping_sleep,
            leadership=leadership,
            stop=stop,
        )
    )

    assert len(worker.windows) == 1
    assert leadership.released == 1
