"""Tests for the in-memory incident store."""

import asyncio
from datetime import UTC, datetime

from rolda.detection import Confidence
from rolda.incidents import Incident, InMemoryIncidentStore


def _incident(rule: str = "span_error", span_id: str = "s1") -> Incident:
    return Incident(
        trace_id="t1",
        rule=rule,
        span_id=span_id,
        evidence="boom",
        confidence=Confidence.HIGH,
        signature="a|span_error|tool|boom",
        path=("root", "tool"),
        detected_at=datetime(2026, 11, 26, tzinfo=UTC),
    )


def test_save_is_idempotent_by_trace_and_rule() -> None:
    store = InMemoryIncidentStore()

    first = asyncio.run(store.save(_incident()))
    again = asyncio.run(store.save(_incident(span_id="s2")))

    assert (first, again) == (True, False)
    assert [i.span_id for i in store.all()] == ["s1"]


def test_different_rules_are_separate_incidents() -> None:
    store = InMemoryIncidentStore()

    asyncio.run(store.save(_incident("span_error")))
    asyncio.run(store.save(_incident("tool_loop")))

    assert len(store.all()) == 2
