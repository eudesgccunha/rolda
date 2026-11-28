"""Checkpoint and leader lock on the real PostgreSQL.

Needs the stack with migration 004 applied (``rolda.entrypoints.migrate``)
and the database variables in the environment.
"""

import asyncio
import os
import secrets
from datetime import UTC, datetime

import pytest

from rolda.adapters.postgres import PostgresCheckpointStore, PostgresLeadership
from rolda.entrypoints.settings import load_settings

pytestmark = pytest.mark.integration


def _dsn() -> str:
    return load_settings(os.environ).postgres_dsn


def test_the_cursor_round_trips_and_is_replaced() -> None:
    store = PostgresCheckpointStore(_dsn())
    name = f"test-{secrets.token_hex(4)}"
    first = datetime(2026, 11, 26, 10, 0, tzinfo=UTC)
    second = datetime(2026, 11, 26, 10, 5, tzinfo=UTC)

    assert asyncio.run(store.get(name)) is None
    asyncio.run(store.set(name, first))
    asyncio.run(store.set(name, second))

    assert asyncio.run(store.get(name)) == second


async def _two_candidates(name: str) -> list[bool]:
    first = PostgresLeadership(_dsn())
    second = PostgresLeadership(_dsn())
    results = [
        await first.try_acquire(name),
        await second.try_acquire(name),
        await first.is_held(),
    ]
    await first.release()
    results.append(await first.is_held())
    results.append(await second.try_acquire(name))
    await second.release()
    return results


def test_only_one_worker_leads_at_a_time_and_the_lock_can_move() -> None:
    name = f"test-{secrets.token_hex(4)}"

    got_first, got_second, first_holds, first_after, second_after = (
        asyncio.run(_two_candidates(name))
    )

    assert got_first is True
    assert got_second is False
    assert first_holds is True
    assert first_after is False
    assert second_after is True
