"""Tests for the readiness probe of the API."""

import asyncio
from collections.abc import Awaitable, Callable

from fastapi import FastAPI

from api_support import ApiClient
from rolda.entrypoints.api import create_app
from rolda.incidents import InMemoryIncidentStore, InMemoryLabelStore
from rolda.traces import InMemorySpanSource

ServeApp = Callable[[FastAPI, str | None], ApiClient]
TOKEN = "a-long-enough-test-token"  # noqa: S105 - fake token for tests


async def _ok() -> None:
    return None


async def _broken() -> None:
    msg = "password authentication failed for user secret-user"
    raise ConnectionError(msg)


async def _slow() -> None:
    await asyncio.sleep(60)


def _app(checks: dict[str, Callable[[], Awaitable[None]]]) -> FastAPI:
    incidents = InMemoryIncidentStore()
    return create_app(
        incidents=incidents,
        labels=InMemoryLabelStore(incidents),
        spans=InMemorySpanSource(),
        token=TOKEN,
        readiness=checks,
        readiness_timeout=0.2,
    )


def test_ready_when_every_dependency_answers(serve_app: ServeApp) -> None:
    client = serve_app(_app({"postgres": _ok, "clickhouse": _ok}), TOKEN)

    reply = client.call("GET", "/ready", send_token=False)

    assert reply.status == 200
    assert reply.json() == {"status": "ready"}


def test_not_ready_names_the_failed_dependency_but_not_the_error(
    serve_app: ServeApp,
) -> None:
    client = serve_app(_app({"postgres": _broken, "clickhouse": _ok}), TOKEN)

    reply = client.call("GET", "/ready", send_token=False)

    assert reply.status == 503
    assert reply.json() == {"status": "unavailable", "failed": ["postgres"]}
    assert "secret-user" not in reply.text


def test_a_hanging_dependency_counts_as_not_ready(serve_app: ServeApp) -> None:
    client = serve_app(_app({"clickhouse": _slow}), TOKEN)

    reply = client.call("GET", "/ready", send_token=False)

    assert reply.status == 503
    assert reply.json()["failed"] == ["clickhouse"]


def test_without_checks_the_app_is_ready(serve_app: ServeApp) -> None:
    client = serve_app(_app({}), TOKEN)

    assert client.call("GET", "/ready", send_token=False).status == 200
