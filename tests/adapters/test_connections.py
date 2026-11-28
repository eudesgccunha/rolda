"""The connection helper uses a pool when it has one."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

from rolda.adapters.postgres import PostgresConnections


class _FakePool:
    def __init__(self) -> None:
        self.borrowed = 0
        self.returned = 0

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[str]:
        self.borrowed += 1
        try:
            yield "pooled-connection"
        finally:
            self.returned += 1


def test_a_pool_lends_its_connections_and_takes_them_back() -> None:
    pool = _FakePool()
    connections = PostgresConnections("postgresql://unused", pool=pool)

    async def use() -> str:
        async with connections.connection() as conn:
            return str(conn)

    assert asyncio.run(use()) == "pooled-connection"
    assert (pool.borrowed, pool.returned) == (1, 1)


def test_a_connection_is_returned_even_when_the_work_fails() -> None:
    pool = _FakePool()
    connections = PostgresConnections("postgresql://unused", pool=pool)

    async def use() -> Any:
        async with connections.connection():
            msg = "query failed"
            raise RuntimeError(msg)

    with pytest.raises(RuntimeError):
        asyncio.run(use())

    assert (pool.borrowed, pool.returned) == (1, 1)
