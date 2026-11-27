"""PostgresIncidentStore against the Compose PostgreSQL.

Needs the stack running and ``POSTGRES_USER`` and ``POSTGRES_PASSWORD`` in
the environment. Run with ``uv run pytest -m integration``.
"""

import asyncio
import os
import secrets
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from rolda.adapters.postgres import PostgresIncidentStore
from rolda.detection import Confidence
from rolda.incidents import Incident, order_key

pytestmark = pytest.mark.integration

# Trace content is untrusted: it must be stored as data, never run as SQL.
HOSTILE_EVIDENCE = "boom'; DROP TABLE incidents; --"


def _dsn() -> str:
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    return f"postgresql://{user}:{password}@127.0.0.1:5432/rolda"


def _incident(trace_id: str, rule: str = "span_error") -> Incident:
    return Incident(
        trace_id=trace_id,
        rule=rule,
        span_id="s1",
        evidence=HOSTILE_EVIDENCE,
        confidence=Confidence.LOW,
        signature="a|span_error|tool|boom",
        path=("root", "tool"),
        detected_at=datetime(2026, 11, 26, 10, tzinfo=UTC),
    )


def _rows(trace_id: str) -> list[tuple[str, str, str, str, list[str]]]:
    with psycopg.connect(_dsn()) as conn:
        cur = conn.execute(
            "SELECT rule, evidence, confidence, signature, path "
            "FROM incidents "
            "WHERE trace_id = %s",
            (trace_id,),
        )
        return cur.fetchall()


def test_save_twice_stores_one_row() -> None:
    store = PostgresIncidentStore(_dsn())
    trace_id = secrets.token_hex(16)

    first = asyncio.run(store.save(_incident(trace_id)))
    again = asyncio.run(store.save(_incident(trace_id)))

    assert (first, again) == (True, False)
    assert _rows(trace_id) == [
        (
            "span_error",
            HOSTILE_EVIDENCE,
            "low",
            "a|span_error|tool|boom",
            ["root", "tool"],
        )
    ]


def test_other_rule_on_same_trace_is_a_new_incident() -> None:
    store = PostgresIncidentStore(_dsn())
    trace_id = secrets.token_hex(16)

    asyncio.run(store.save(_incident(trace_id, "span_error")))
    created = asyncio.run(store.save(_incident(trace_id, "tool_loop")))

    assert created is True
    assert len(_rows(trace_id)) == 2


def test_list_filters_pages_and_reads_back_a_trace() -> None:
    store = PostgresIncidentStore(_dsn())
    agent = f"agent-{secrets.token_hex(4)}"
    ids = [secrets.token_hex(16) for _ in range(3)]
    for index, trace_id in enumerate(ids):
        incident = Incident(
            trace_id=trace_id,
            rule="span_error",
            span_id="s1",
            evidence="boom",
            confidence=Confidence.LOW,
            signature=f"{agent}|span_error|tool|boom",
            path=("root", "tool"),
            detected_at=datetime(2026, 11, 26, 10, index, tzinfo=UTC),
        )
        asyncio.run(store.save(incident))

    first = asyncio.run(store.list(agent=agent, limit=2))
    second = asyncio.run(
        store.list(agent=agent, limit=2, after=order_key(first[-1]))
    )

    assert [i.trace_id for i in first] == [ids[2], ids[1]]
    assert [i.trace_id for i in second] == [ids[0]]
    assert asyncio.run(store.list(rule="no_such_rule", agent=agent)) == []
    [found] = asyncio.run(store.for_trace(ids[0]))
    assert found.evidence == "boom"
    assert found.path == ("root", "tool")


def test_alerts_are_queued_with_the_incident_and_retried() -> None:
    store = PostgresIncidentStore(_dsn())
    trace_id = secrets.token_hex(16)
    window = timedelta(seconds=0)

    created = asyncio.run(
        store.save(_incident(trace_id), channels=["slack", "teams"])
    )
    again = asyncio.run(store.save(_incident(trace_id), channels=["slack"]))

    def mine() -> list[str]:
        found = asyncio.run(
            store.pending(limit=500, max_attempts=3, backoff=window)
        )
        return sorted(
            d.channel for d in found if d.incident.trace_id == trace_id
        )

    assert (created, again) == (True, False)
    assert mine() == ["slack", "teams"]

    asyncio.run(
        store.mark_delivery(trace_id, "span_error", "slack", delivered=True)
    )
    assert mine() == ["teams"]

    for _ in range(3):
        asyncio.run(
            store.mark_delivery(
                trace_id, "span_error", "teams", delivered=False
            )
        )
    assert mine() == []
