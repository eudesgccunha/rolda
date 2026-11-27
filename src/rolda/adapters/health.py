"""Reachability checks for the databases, used by the readiness probe."""

import asyncio
from collections.abc import Awaitable, Callable

import clickhouse_connect
import psycopg

from rolda.entrypoints.settings import Settings

_TIMEOUT_SECONDS = 3


def postgres_check(dsn: str) -> Callable[[], Awaitable[None]]:
    """Return a check that runs ``SELECT 1`` on PostgreSQL."""

    async def check() -> None:
        async with await psycopg.AsyncConnection.connect(
            dsn, connect_timeout=_TIMEOUT_SECONDS
        ) as conn:
            await conn.execute("SELECT 1")

    return check


def clickhouse_check(settings: Settings) -> Callable[[], Awaitable[None]]:
    """Return a check that runs ``SELECT 1`` on ClickHouse."""

    def run() -> None:
        client = clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            connect_timeout=_TIMEOUT_SECONDS,
            send_receive_timeout=_TIMEOUT_SECONDS,
        )
        try:
            client.command("SELECT 1")
        finally:
            client.close()

    async def check() -> None:
        await asyncio.to_thread(run)

    return check
