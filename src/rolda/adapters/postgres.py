"""PostgreSQL adapter for the ``IncidentStore`` port."""

from collections.abc import Sequence
from typing import Any

import psycopg

from rolda.detection import Confidence
from rolda.incidents import (
    Incident,
    Label,
    LabelSource,
    OrderKey,
    UnknownIncidentError,
)
from rolda.judge import Verdict

_INSERT = """
INSERT INTO incidents
    (trace_id, rule, span_id, evidence, confidence, signature, path,
     detected_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (trace_id, rule) DO NOTHING
"""


_LIST = """
SELECT trace_id, rule, span_id, evidence, confidence, signature, path,
       detected_at
FROM incidents
WHERE (%(rule)s::text IS NULL OR rule = %(rule)s::text)
  AND (%(agent)s::text IS NULL
       OR split_part(signature, '|', 1) = %(agent)s::text)
  AND (%(after_time)s::timestamptz IS NULL
       OR (detected_at, trace_id, rule)
          < (%(after_time)s::timestamptz, %(after_trace)s::text,
             %(after_rule)s::text))
ORDER BY detected_at DESC, trace_id DESC, rule DESC
LIMIT %(limit)s
"""

_FOR_TRACE = """
SELECT trace_id, rule, span_id, evidence, confidence, signature, path,
       detected_at
FROM incidents
WHERE trace_id = %s
ORDER BY rule
"""


def _incident(row: Sequence[Any]) -> Incident:
    return Incident(
        trace_id=row[0],
        rule=row[1],
        span_id=row[2],
        evidence=row[3],
        confidence=Confidence(row[4]),
        signature=row[5],
        path=tuple(row[6]),
        detected_at=row[7],
    )


class PostgresIncidentStore:
    """Store incidents in PostgreSQL, one row per trace and rule."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    async def save(self, incident: Incident) -> bool:
        """Insert the incident. Return True when the row is new."""
        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            cursor = await conn.execute(
                _INSERT,
                (
                    incident.trace_id,
                    incident.rule,
                    incident.span_id,
                    incident.evidence,
                    incident.confidence.value,
                    incident.signature,
                    list(incident.path),
                    incident.detected_at,
                ),
            )
            return cursor.rowcount == 1

    async def list(
        self,
        *,
        rule: str | None = None,
        agent: str | None = None,
        limit: int = 50,
        after: OrderKey | None = None,
    ) -> Sequence[Incident]:
        """Return incidents newest first, with filters and a cursor."""
        params = {
            "rule": rule,
            "agent": agent,
            "limit": limit,
            "after_time": after[0] if after else None,
            "after_trace": after[1] if after else None,
            "after_rule": after[2] if after else None,
        }
        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            cursor = await conn.execute(_LIST, params)
            rows = await cursor.fetchall()
        return [_incident(row) for row in rows]

    async def for_trace(self, trace_id: str) -> Sequence[Incident]:
        """Return every incident of one trace."""
        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            cursor = await conn.execute(_FOR_TRACE, (trace_id,))
            rows = await cursor.fetchall()
        return [_incident(row) for row in rows]


_UPSERT_LABEL = """
INSERT INTO labels
    (trace_id, rule, source, verdict, reason, labeler, labeled_at)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (trace_id, rule, source) DO UPDATE SET
    verdict = EXCLUDED.verdict,
    reason = EXCLUDED.reason,
    labeler = EXCLUDED.labeler,
    labeled_at = EXCLUDED.labeled_at
"""

_LABELED = """
SELECT i.trace_id, i.rule, i.span_id, i.evidence, i.confidence,
       i.signature, i.path, i.detected_at,
       l.verdict, l.reason, l.labeler, l.labeled_at
FROM labels l
JOIN incidents i ON i.trace_id = l.trace_id AND i.rule = l.rule
WHERE l.source = %s
ORDER BY l.labeled_at
"""


_LABELS_FOR_TRACE = """
SELECT trace_id, rule, source, verdict, reason, labeler, labeled_at
FROM labels WHERE trace_id = %s ORDER BY rule, source
"""


class PostgresLabelStore:
    """Store labels in PostgreSQL, one row per incident and source."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    async def upsert(self, label: Label) -> None:
        """Insert or replace a label for an existing incident."""
        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            try:
                await conn.execute(
                    _UPSERT_LABEL,
                    (
                        label.trace_id,
                        label.rule,
                        label.source.value,
                        label.verdict.value,
                        label.reason,
                        label.labeler,
                        label.labeled_at,
                    ),
                )
            except psycopg.errors.ForeignKeyViolation as exc:
                msg = (
                    f"no incident for trace {label.trace_id} rule {label.rule}"
                )
                raise UnknownIncidentError(msg) from exc

    async def for_trace(self, trace_id: str) -> Sequence[Label]:
        """Return the labels of every incident of one trace."""
        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            cursor = await conn.execute(_LABELS_FOR_TRACE, (trace_id,))
            rows = await cursor.fetchall()
        return [
            Label(
                trace_id=row[0],
                rule=row[1],
                source=LabelSource(row[2]),
                verdict=Verdict(row[3]),
                reason=row[4],
                labeler=row[5],
                labeled_at=row[6],
            )
            for row in rows
        ]

    async def labeled(
        self, source: LabelSource
    ) -> Sequence[tuple[Incident, Label]]:
        """Return labeled incidents from one source."""
        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            cursor = await conn.execute(_LABELED, (source.value,))
            rows = await cursor.fetchall()
        return [
            (
                _incident(row[:8]),
                Label(
                    trace_id=row[0],
                    rule=row[1],
                    source=source,
                    verdict=Verdict(row[8]),
                    reason=row[9],
                    labeler=row[10],
                    labeled_at=row[11],
                ),
            )
            for row in rows
        ]
