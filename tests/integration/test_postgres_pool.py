"""The connection pool on the real PostgreSQL.

Needs the stack with migrations applied and the database variables in the
environment.
"""

import asyncio
import os
import secrets
from datetime import UTC, datetime

import pytest
from psycopg_pool import AsyncConnectionPool

from rolda.adapters.postgres import PostgresIncidentStore
from rolda.detection import Confidence
from rolda.entrypoints.settings import load_settings
from rolda.incidents import Incident

pytestmark = pytest.mark.integration


def _incident(agent: str, number: int) -> Incident:
    return Incident(
        trace_id=secrets.token_hex(16),
        rule="span_error",
        span_id=f"s{number}",
        evidence="boom",
        confidence=Confidence.LOW,
        signature=f"{agent}|span_error|tool|boom",
        path=("root", "tool"),
        detected_at=datetime.now(UTC),
    )


async def _many_saves(dsn: str, agent: str, count: int) -> tuple[int, int]:
    pool = AsyncConnectionPool(dsn, min_size=1, max_size=3, open=False)
    await pool.open()
    try:
        store = PostgresIncidentStore(dsn, pool)
        results = await asyncio.gather(
            *(store.save(_incident(agent, n)) for n in range(count))
        )
        stored = await store.list(agent=agent, limit=count + 10)
        return sum(results), len(stored)
    finally:
        await pool.close()


def test_many_concurrent_saves_share_a_few_connections() -> None:
    dsn = load_settings(os.environ).postgres_dsn
    agent = f"pool-agent-{secrets.token_hex(4)}"

    created, stored = asyncio.run(_many_saves(dsn, agent, 60))

    assert created == 60
    assert stored == 60  # found through the indexed agent column
