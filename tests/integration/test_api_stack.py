"""The API on the real PostgreSQL and ClickHouse.

Needs the Compose stack (with migrations applied) and the four database
variables in the environment. Run with ``uv run pytest -m integration``.
"""

import asyncio
import os
import secrets
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI

from api_support import ApiClient
from rolda.adapters.clickhouse import ClickHouseSpanSource
from rolda.adapters.postgres import PostgresIncidentStore, PostgresLabelStore
from rolda.detection import Confidence
from rolda.entrypoints.api import create_app
from rolda.entrypoints.settings import load_settings
from rolda.incidents import Incident

pytestmark = pytest.mark.integration

ServeApp = Callable[[FastAPI, str | None], ApiClient]
TOKEN = "integration-test-token-123"  # noqa: S105 - fake token for tests


def test_list_label_and_read_back_on_the_real_stores(
    serve_app: ServeApp,
) -> None:
    settings = load_settings(os.environ)
    agent = f"api-agent-{secrets.token_hex(4)}"
    trace_id = secrets.token_hex(16)
    asyncio.run(
        PostgresIncidentStore(settings.postgres_dsn).save(
            Incident(
                trace_id=trace_id,
                rule="span_error",
                span_id="s1",
                evidence="boom",
                confidence=Confidence.HIGH,
                signature=f"{agent}|span_error|tool|boom",
                path=("root", "tool"),
                detected_at=datetime.now(UTC),
            )
        )
    )
    app = create_app(
        incidents=PostgresIncidentStore(settings.postgres_dsn),
        labels=PostgresLabelStore(settings.postgres_dsn),
        spans=ClickHouseSpanSource(settings),
        token=TOKEN,
    )
    client = serve_app(app, TOKEN)

    listed = client.call("GET", f"/incidents?agent={agent}").json()
    put = client.call(
        "PUT",
        f"/incidents/{trace_id}/span_error/label",
        body={"verdict": "failure", "reason": "api test", "labeler": "test"},
    )
    detail = client.call("GET", f"/incidents/{trace_id}").json()
    export = client.call("GET", "/evals/export")

    assert [i["trace_id"] for i in listed["items"]] == [trace_id]
    assert put.status == 200
    assert [x["verdict"] for x in detail["labels"]] == ["failure"]
    assert export.status == 200
