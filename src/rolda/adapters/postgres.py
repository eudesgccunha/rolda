"""PostgreSQL adapter for the ``IncidentStore`` port."""

import psycopg

from rolda.incidents import Incident

_INSERT = """
INSERT INTO incidents
    (trace_id, rule, span_id, evidence, confidence, signature, path,
     detected_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (trace_id, rule) DO NOTHING
"""


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
