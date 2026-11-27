"""Tests for the ClickHouse row conversion (no database needed)."""

from datetime import UTC, datetime
from typing import Any

from rolda.adapters.clickhouse import rows_to_spans


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "Timestamp": datetime(2026, 11, 26, 10, 0, 0, 123456),
        "TraceId": "t1",
        "SpanId": "s1",
        "ParentSpanId": "",
        "SpanName": "chat m",
        "SpanKind": "Client",
        "ServiceName": "svc",
        "ResourceAttributes": {},
        "SpanAttributes": {"gen_ai.operation.name": "chat"},
        "Duration": 5,
        "StatusCode": "Error",
        "StatusMessage": "boom",
    }
    row.update(overrides)
    return row


def test_valid_rows_become_spans() -> None:
    spans, skipped = rows_to_spans([_row()])

    assert skipped == 0
    assert spans[0].trace_id == "t1"
    assert spans[0].started_at == datetime(
        2026, 11, 26, 10, 0, 0, 123456, tzinfo=UTC
    )


def test_invalid_rows_are_counted_and_skipped() -> None:
    rows = [_row(), _row(TraceId=""), _row(SpanId="s2", Timestamp="bad")]

    spans, skipped = rows_to_spans(rows)

    assert [s.span_id for s in spans] == ["s1"]
    assert skipped == 2
