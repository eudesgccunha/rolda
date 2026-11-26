"""End to end: OTLP span -> ClickHouse -> worker -> PostgreSQL incident.

Needs the Compose stack and ``CLICKHOUSE_USER``, ``CLICKHOUSE_PASSWORD``,
``POSTGRES_USER`` and ``POSTGRES_PASSWORD`` in the environment.
"""

import asyncio
import http.client
import json
import os
import secrets
import time
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from rolda.adapters.clickhouse import ClickHouseSpanSource
from rolda.adapters.postgres import PostgresIncidentStore
from rolda.detection import DetectionConfig, default_rules
from rolda.entrypoints.settings import load_settings
from rolda.entrypoints.worker import Worker, WorkerConfig

pytestmark = pytest.mark.integration


def _send_failing_span(trace_id: str) -> None:
    now = time.time_ns()
    span = {
        "traceId": trace_id,
        "spanId": secrets.token_hex(8),
        "name": "execute_tool search",
        "kind": 1,
        "startTimeUnixNano": str(now),
        "endTimeUnixNano": str(now + 1_000_000),
        "status": {"code": 2, "message": "timeout"},
        "attributes": [
            {
                "key": "gen_ai.operation.name",
                "value": {"stringValue": "execute_tool"},
            }
        ],
    }
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": "e2e-agent"},
                        }
                    ]
                },
                "scopeSpans": [{"scope": {"name": "e2e"}, "spans": [span]}],
            }
        ]
    }
    conn = http.client.HTTPConnection("127.0.0.1", 4318, timeout=10)
    try:
        conn.request(
            "POST",
            "/v1/traces",
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        response.read()
        assert response.status == 200
    finally:
        conn.close()


def _incident_count(dsn: str, trace_id: str) -> int:
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT count(*) FROM incidents WHERE trace_id = %s",
            (trace_id,),
        ).fetchone()
    assert row is not None
    return int(row[0])


def test_failing_span_becomes_one_incident_even_when_reprocessed() -> None:
    settings = load_settings(os.environ)
    source = ClickHouseSpanSource(settings)
    worker = Worker(
        source=source,
        store=PostgresIncidentStore(settings.postgres_dsn),
        rules=default_rules(DetectionConfig()),
        config=WorkerConfig(),
    )
    trace_id = secrets.token_hex(16)
    _send_failing_span(trace_id)

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        end = datetime.now(UTC) + timedelta(minutes=1)
        asyncio.run(worker.run_window(end - timedelta(minutes=10), end))
        if _incident_count(settings.postgres_dsn, trace_id):
            break
        time.sleep(1)

    end = datetime.now(UTC) + timedelta(minutes=1)
    asyncio.run(worker.run_window(end - timedelta(minutes=10), end))

    assert _incident_count(settings.postgres_dsn, trace_id) == 1
