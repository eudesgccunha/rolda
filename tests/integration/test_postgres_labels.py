"""PostgresLabelStore against the Compose PostgreSQL.

Needs the stack with ``003_labels.sql`` applied and ``POSTGRES_USER`` and
``POSTGRES_PASSWORD`` in the environment.
"""

import asyncio
import os
import secrets
from datetime import UTC, datetime

import pytest

from rolda.adapters.postgres import PostgresIncidentStore, PostgresLabelStore
from rolda.detection import Confidence
from rolda.incidents import (
    Incident,
    Label,
    LabelSource,
    UnknownIncidentError,
)
from rolda.judge import Verdict

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 26, 12, tzinfo=UTC)


def _dsn() -> str:
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    return f"postgresql://{user}:{password}@127.0.0.1:5432/rolda"


def _label(trace_id: str, verdict: Verdict, source: LabelSource) -> Label:
    return Label(
        trace_id=trace_id,
        rule="span_error",
        source=source,
        verdict=verdict,
        reason="because",
        labeler="ana",
        labeled_at=NOW,
    )


def _incident(trace_id: str) -> Incident:
    return Incident(
        trace_id=trace_id,
        rule="span_error",
        span_id="s1",
        evidence="boom",
        confidence=Confidence.HIGH,
        signature="a|span_error|tool|boom",
        path=("root", "tool"),
        detected_at=NOW,
    )


def test_label_round_trip_and_replacement() -> None:
    incidents = PostgresIncidentStore(_dsn())
    labels = PostgresLabelStore(_dsn())
    trace_id = secrets.token_hex(16)
    asyncio.run(incidents.save(_incident(trace_id)))

    asyncio.run(
        labels.upsert(_label(trace_id, Verdict.FAILURE, LabelSource.HUMAN))
    )
    asyncio.run(
        labels.upsert(_label(trace_id, Verdict.FALSE_ALARM, LabelSource.HUMAN))
    )

    found = [
        (incident, label)
        for incident, label in asyncio.run(labels.labeled(LabelSource.HUMAN))
        if label.trace_id == trace_id
    ]
    assert len(found) == 1
    assert found[0][1].verdict is Verdict.FALSE_ALARM
    assert found[0][0].path == ("root", "tool")


def test_label_for_unknown_incident_is_rejected() -> None:
    labels = PostgresLabelStore(_dsn())

    with pytest.raises(UnknownIncidentError):
        asyncio.run(
            labels.upsert(_label("f" * 32, Verdict.FAILURE, LabelSource.HUMAN))
        )
