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
from rolda.adapters.postgres import (
    PostgresIncidentStore,
    PostgresLabelStore,
)
from rolda.detection import DetectionConfig, default_rules
from rolda.entrypoints.settings import load_settings
from rolda.entrypoints.worker import Worker, WorkerConfig
from rolda.evals import build_cases
from rolda.incidents import Label, LabelSource
from rolda.judge import Verdict

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


def test_labeled_incident_exports_as_an_eval_case() -> None:
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
    assert _incident_count(settings.postgres_dsn, trace_id) == 1

    labels = PostgresLabelStore(settings.postgres_dsn)
    asyncio.run(
        labels.upsert(
            Label(
                trace_id=trace_id,
                rule="span_error",
                source=LabelSource.HUMAN,
                verdict=Verdict.FAILURE,
                reason="e2e",
                labeler="test",
                labeled_at=datetime.now(UTC),
            )
        )
    )

    cases = asyncio.run(build_cases(labels, source))

    [case] = [c for c in cases if c.trace_id == trace_id]
    assert case.expected == "incident"
    assert [s.status for s in case.spans] == ["error"]
    assert case.spans[0].operation == "tool"


def test_spans_are_read_back_by_trace_id_in_a_batch() -> None:
    source = ClickHouseSpanSource(load_settings(os.environ))
    first, second = secrets.token_hex(16), secrets.token_hex(16)
    _send_failing_span(first)
    _send_failing_span(second)

    deadline = time.monotonic() + 30
    found: set[str] = set()
    while time.monotonic() < deadline and found != {first, second}:
        spans = asyncio.run(source.spans_for_traces([first, second, "0" * 32]))
        found = {span.trace_id for span in spans}
        time.sleep(1)

    assert found == {first, second}
