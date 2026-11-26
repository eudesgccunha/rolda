"""ClickHouse adapter for the ``SpanSource`` port."""

import asyncio
import logging
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import clickhouse_connect

from rolda.entrypoints.settings import Settings
from rolda.traces import NormalizationError, Span, normalize_span

logger = logging.getLogger(__name__)

_QUERY = """
SELECT Timestamp, TraceId, SpanId, ParentSpanId, SpanName, SpanKind,
       ServiceName, ResourceAttributes, SpanAttributes, Duration,
       StatusCode, StatusMessage
FROM otel_traces
WHERE Timestamp >= {start:DateTime64(9)}
  AND Timestamp < {end:DateTime64(9)}
ORDER BY Timestamp
"""


def rows_to_spans(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[list[Span], int]:
    """Normalize rows. Return the spans and how many rows were skipped."""
    spans: list[Span] = []
    skipped = 0
    for row in rows:
        try:
            spans.append(normalize_span(row))
        except NormalizationError:
            skipped += 1
    return spans, skipped


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


class ClickHouseSpanSource:
    """Read spans written by the Collector ``clickhouse`` exporter."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.skipped_rows = 0

    def _query(self, start: datetime, end: datetime) -> Sequence[Span]:
        client = clickhouse_connect.get_client(
            host=self._settings.clickhouse_host,
            port=self._settings.clickhouse_port,
            username=self._settings.clickhouse_user,
            password=self._settings.clickhouse_password,
            database="rolda",
        )
        try:
            result = client.query(
                _QUERY,
                parameters={
                    "start": _naive_utc(start),
                    "end": _naive_utc(end),
                },
            )
            spans, skipped = rows_to_spans(result.named_results())
        finally:
            client.close()
        if skipped:
            self.skipped_rows += skipped
            logger.warning("skipped %d invalid span rows", skipped)
        return spans

    async def spans_between(
        self, start: datetime, end: datetime
    ) -> Sequence[Span]:
        """Return spans that started in ``[start, end)``."""
        return await asyncio.to_thread(self._query, start, end)
