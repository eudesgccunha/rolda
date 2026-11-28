"""PostgreSQL and ClickHouse adapters for the ``MigrationTarget`` port."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import clickhouse_connect
import psycopg

from rolda.entrypoints.settings import Settings
from rolda.migrations import Migration, split_statements

# Any constant works: it only has to be the same for every runner.
_LOCK_KEY = 7_283_410_001

_PG_BOOKKEEPING = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    text        PRIMARY KEY,
    checksum   text        NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


class PostgresMigrationTarget:
    """Apply migrations to PostgreSQL, one transaction per file."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn: psycopg.AsyncConnection | None = None

    def _connection(self) -> psycopg.AsyncConnection:
        if self._conn is None:
            msg = "use the target inside 'async with target.locked()'"
            raise RuntimeError(msg)
        return self._conn

    @asynccontextmanager
    async def locked(self) -> AsyncIterator[None]:
        """Open a connection and hold an advisory lock on it."""
        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            self._conn = conn
            try:
                await conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))
                await conn.execute(_PG_BOOKKEEPING)
                await conn.commit()
                yield
            finally:
                self._conn = None

    async def applied(self) -> dict[str, str]:
        """Return the recorded versions and their checksums."""
        cursor = await self._connection().execute(
            "SELECT version, checksum FROM schema_migrations"
        )
        return {row[0]: row[1] for row in await cursor.fetchall()}

    async def apply(self, migration: Migration) -> None:
        """Run the file and record it in the same transaction."""
        conn = self._connection()
        async with conn.transaction():
            await conn.execute(migration.sql)
            await conn.execute(
                "INSERT INTO schema_migrations (version, checksum) "
                "VALUES (%s, %s)",
                (migration.version, migration.checksum),
            )


_CH_BOOKKEEPING = (
    "CREATE DATABASE IF NOT EXISTS rolda",
    """
CREATE TABLE IF NOT EXISTS rolda.schema_migrations (
    version    String,
    checksum   String,
    applied_at DateTime DEFAULT now()
) ENGINE = MergeTree ORDER BY version
""",
)


class ClickHouseMigrationTarget:
    """Apply migrations to ClickHouse. DDL is not transactional there."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client(self) -> clickhouse_connect.driver.Client:
        return clickhouse_connect.get_client(
            host=self._settings.clickhouse_host,
            port=self._settings.clickhouse_port,
            username=self._settings.clickhouse_user,
            password=self._settings.clickhouse_password,
        )

    @asynccontextmanager
    async def locked(self) -> AsyncIterator[None]:
        """ClickHouse has no advisory lock. The statements are idempotent."""
        yield

    def _applied(self) -> dict[str, str]:
        client = self._client()
        try:
            for statement in _CH_BOOKKEEPING:
                client.command(statement)
            result = client.query(
                "SELECT version, checksum FROM rolda.schema_migrations"
            )
            return {row[0]: row[1] for row in result.result_rows}
        finally:
            client.close()

    async def applied(self) -> dict[str, str]:
        """Return the recorded versions and their checksums."""
        return await asyncio.to_thread(self._applied)

    def _apply(self, migration: Migration) -> None:
        client = self._client()
        try:
            for statement in split_statements(migration.sql):
                client.command(statement)
            client.insert(
                "rolda.schema_migrations",
                [[migration.version, migration.checksum]],
                column_names=["version", "checksum"],
            )
        finally:
            client.close()

    async def apply(self, migration: Migration) -> None:
        """Run each statement, then record the file."""
        await asyncio.to_thread(self._apply, migration)
