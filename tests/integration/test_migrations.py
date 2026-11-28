"""The migration runner against the real databases.

Needs the Compose stack and the four database variables in the
environment. Running it twice must change nothing the second time.
"""

import asyncio
import os
from pathlib import Path

import pytest

from rolda.adapters.migrations import (
    ClickHouseMigrationTarget,
    PostgresMigrationTarget,
)
from rolda.entrypoints.migrate import MIGRATIONS
from rolda.entrypoints.settings import load_settings
from rolda.migrations import apply_pending, load_migrations

pytestmark = pytest.mark.integration


def _versions(engine: str) -> list[str]:
    return [m.version for m in load_migrations(Path(MIGRATIONS / engine))]


def test_postgres_migrations_are_recorded_and_repeatable() -> None:
    settings = load_settings(os.environ)
    migrations = load_migrations(MIGRATIONS / "postgres")

    asyncio.run(
        apply_pending(
            PostgresMigrationTarget(settings.postgres_dsn), migrations
        )
    )
    again = asyncio.run(
        apply_pending(
            PostgresMigrationTarget(settings.postgres_dsn), migrations
        )
    )

    assert again == []
    recorded = asyncio.run(_recorded_postgres(settings.postgres_dsn))
    assert set(_versions("postgres")) <= set(recorded)


async def _recorded_postgres(dsn: str) -> dict[str, str]:
    target = PostgresMigrationTarget(dsn)
    async with target.locked():
        return await target.applied()


def test_clickhouse_migrations_are_recorded_and_repeatable() -> None:
    settings = load_settings(os.environ)
    migrations = load_migrations(MIGRATIONS / "clickhouse")
    target = ClickHouseMigrationTarget(settings)

    asyncio.run(apply_pending(target, migrations))
    again = asyncio.run(apply_pending(target, migrations))

    assert again == []
    assert set(_versions("clickhouse")) <= set(asyncio.run(target.applied()))
