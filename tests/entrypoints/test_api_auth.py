"""Tests for API authentication and the health check."""

from collections.abc import Callable

import pytest
from fastapi import FastAPI

from api_support import ApiClient
from rolda.entrypoints.api import create_app
from rolda.incidents import InMemoryIncidentStore, InMemoryLabelStore
from rolda.traces import InMemorySpanSource

TOKEN = "a-long-enough-test-token"  # noqa: S105 - fake token for tests


ServeApp = Callable[[FastAPI, str | None], ApiClient]


def _app(docs: bool = False) -> FastAPI:
    incidents = InMemoryIncidentStore()
    return create_app(
        incidents=incidents,
        labels=InMemoryLabelStore(incidents),
        spans=InMemorySpanSource(),
        token=TOKEN,
        docs=docs,
    )


def test_health_needs_no_token(serve_app: ServeApp) -> None:
    client = serve_app(_app(), TOKEN)

    reply = client.call("GET", "/health", send_token=False)

    assert reply.status == 200
    assert reply.json() == {"status": "ok"}


def test_requests_without_a_token_are_rejected(serve_app: ServeApp) -> None:
    client = serve_app(_app(), TOKEN)

    reply = client.call("GET", "/incidents", send_token=False)

    assert reply.status == 401
    assert reply.headers["www-authenticate"] == "Bearer"


def test_wrong_token_is_rejected(serve_app: ServeApp) -> None:
    client = serve_app(_app(), TOKEN)

    reply = client.call("GET", "/incidents", token="not-the-token")  # noqa: S106 - fake token

    assert reply.status == 401


def test_valid_token_is_accepted(serve_app: ServeApp) -> None:
    client = serve_app(_app(), TOKEN)

    assert client.call("GET", "/incidents").status == 200


def test_docs_are_off_by_default(serve_app: ServeApp) -> None:
    client = serve_app(_app(), TOKEN)

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.call("GET", path, send_token=False).status == 404


def test_docs_can_be_turned_on(serve_app: ServeApp) -> None:
    client = serve_app(_app(docs=True), TOKEN)

    assert client.call("GET", "/openapi.json", send_token=False).status == 200


def test_a_short_token_is_refused_at_creation() -> None:
    incidents = InMemoryIncidentStore()
    labels = InMemoryLabelStore(incidents)
    spans = InMemorySpanSource()

    with pytest.raises(ValueError, match="token"):
        create_app(
            incidents=incidents,
            labels=labels,
            spans=spans,
            token="short",  # noqa: S106 - deliberately too short
        )


def test_the_bearer_scheme_is_case_insensitive(serve_app: ServeApp) -> None:
    client = serve_app(_app(), TOKEN)

    for scheme in ("bearer", "BEARER", "Bearer"):
        reply = client.call(
            "GET", "/incidents", headers={"Authorization": f"{scheme} {TOKEN}"}
        )
        assert reply.status == 200, scheme


def test_other_schemes_are_rejected(serve_app: ServeApp) -> None:
    client = serve_app(_app(), TOKEN)

    reply = client.call(
        "GET", "/incidents", headers={"Authorization": f"Basic {TOKEN}"}
    )

    assert reply.status == 401
