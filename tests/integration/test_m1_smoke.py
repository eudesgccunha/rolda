"""M1 acceptance: a test span sent over OTLP is queryable in ClickHouse.

Needs the Compose stack (``deploy/compose``) running and these variables
in the environment: ``CLICKHOUSE_USER`` and ``CLICKHOUSE_PASSWORD``.
Run with ``uv run pytest -m integration``.
"""

import base64
import http.client
import json
import os
import secrets
import time
import urllib.parse

import pytest

pytestmark = pytest.mark.integration

OTLP_HOST = "127.0.0.1"
OTLP_HTTP_PORT = 4318
CLICKHOUSE_HTTP_PORT = 8123
WAIT_SECONDS = 30.0


def _send_span(trace_id: str, span_id: str) -> None:
    now = time.time_ns()
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": "m1-smoke"},
                        }
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "rolda.tests"},
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": span_id,
                                "name": "smoke-span",
                                "kind": 1,
                                "startTimeUnixNano": str(now),
                                "endTimeUnixNano": str(now + 1_000_000),
                            }
                        ],
                    }
                ],
            }
        ]
    }
    conn = http.client.HTTPConnection(OTLP_HOST, OTLP_HTTP_PORT, timeout=10)
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


def _count_spans(trace_id: str) -> int:
    user = os.environ["CLICKHOUSE_USER"]
    password = os.environ["CLICKHOUSE_PASSWORD"]
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    query = urllib.parse.urlencode(
        {
            "query": (
                "SELECT count() FROM rolda.otel_traces "
                "WHERE TraceId = {trace_id:String}"
            ),
            "param_trace_id": trace_id,
        }
    )
    conn = http.client.HTTPConnection(
        OTLP_HOST, CLICKHOUSE_HTTP_PORT, timeout=10
    )
    try:
        conn.request(
            "GET",
            f"/?{query}",
            headers={"Authorization": f"Basic {token}"},
        )
        response = conn.getresponse()
        body = response.read().decode().strip()
        assert response.status == 200, body
        return int(body)
    finally:
        conn.close()


def test_span_sent_over_otlp_is_queryable() -> None:
    trace_id = secrets.token_hex(16)
    span_id = secrets.token_hex(8)

    _send_span(trace_id, span_id)

    deadline = time.monotonic() + WAIT_SECONDS
    count = 0
    while time.monotonic() < deadline:
        count = _count_spans(trace_id)
        if count:
            break
        time.sleep(1)

    assert count == 1
