"""ClickHouse adapter for the ``SpanSource`` port."""

import asyncio
import logging
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import clickhouse_connect

from rolda.entrypoints.settings import Settings
from rolda.traces import NormalizationError, Shard, Span, normalize_span

logger = logging.getLogger(__name__)

_QUERY = """
SELECT Timestamp, TraceId, SpanId, ParentSpanId, SpanName, SpanKind,
       ServiceName, ResourceAttributes, SpanAttributes, Duration,
       StatusCode, StatusMessage
FROM otel_traces
WHERE Timestamp >= {start:DateTime64(9)}
  AND Timestamp < {end:DateTime64(9)}
  AND ({shards:UInt32} = 1
       OR CRC32(TraceId) % {shards:UInt32} = {shard:UInt32})
ORDER BY Timestamp
"""

_TRACE_QUERY = """
SELECT Timestamp, TraceId, SpanId, ParentSpanId, SpanName, SpanKind,
       ServiceName, ResourceAttributes, SpanAttributes, Duration,
       StatusCode, StatusMessage
FROM otel_traces
WHERE TraceId = {trace_id:String}
ORDER BY Timestamp
"""


_TRACES_QUERY = """
SELECT Timestamp, TraceId, SpanId, ParentSpanId, SpanName, SpanKind,
       ServiceName, ResourceAttributes, SpanAttributes, Duration,
       StatusCode, StatusMessage
FROM otel_traces
WHERE TraceId IN {trace_ids:Array(String)}
ORDER BY Timestamp
"""

_TRACE_ID_BATCH = 500


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

    def __init__(self, settings: Settings, shard: Shard | None = None) -> None:
        self._settings = settings
        self._shard = shard or Shard.single()
        self.skipped_rows = 0

    def _run(self, sql: str, parameters: dict[str, Any]) -> Sequence[Span]:
        client = clickhouse_connect.get_client(
            host=self._settings.clickhouse_host,
            port=self._settings.clickhouse_port,
            username=self._settings.clickhouse_user,
            password=self._settings.clickhouse_password,
            database="rolda",
        )
        try:
            result = client.query(sql, parameters=parameters)
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
        parameters: dict[str, Any] = {
            "start": _naive_utc(start),
            "end": _naive_utc(end),
            "shards": self._shard.count,
            "shard": self._shard.index,
        }
        return await asyncio.to_thread(self._run, _QUERY, parameters)

    async def spans_for_trace(self, trace_id: str) -> Sequence[Span]:
        """Return every span of one trace."""
        return await asyncio.to_thread(
            self._run, _TRACE_QUERY, {"trace_id": trace_id}
        )

    async def spans_for_traces(
        self, trace_ids: Sequence[str]
    ) -> Sequence[Span]:
        """Return every span of each trace, reading ids in batches."""
        found: list[Span] = []
        for index in range(0, len(trace_ids), _TRACE_ID_BATCH):
            batch = list(trace_ids[index : index + _TRACE_ID_BATCH])
            found.extend(
                await asyncio.to_thread(
                    self._run, _TRACES_QUERY, {"trace_ids": batch}
                )
            )
        return found
