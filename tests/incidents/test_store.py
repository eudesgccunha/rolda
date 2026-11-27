"""Tests for the in-memory incident store."""

import asyncio
from datetime import UTC, datetime

from rolda.detection import Confidence
from rolda.incidents import Incident, InMemoryIncidentStore, order_key


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


def _at(
    minute: int,
    *,
    trace_id: str = "t1",
    rule: str = "span_error",
    agent: str = "a",
) -> Incident:
    return Incident(
        trace_id=trace_id,
        rule=rule,
        span_id="s1",
        evidence="boom",
        confidence=Confidence.HIGH,
        signature=f"{agent}|{rule}|tool|boom",
        path=("root", "tool"),
        detected_at=datetime(2026, 11, 26, 10, minute, tzinfo=UTC),
    )


def _filled() -> InMemoryIncidentStore:
    store = InMemoryIncidentStore()
    for incident in (
        _at(1, trace_id="t1"),
        _at(2, trace_id="t2", rule="tool_loop", agent="b"),
        _at(3, trace_id="t3"),
        _at(4, trace_id="t4", agent="b"),
    ):
        asyncio.run(store.save(incident))
    return store


def test_list_returns_newest_first() -> None:
    store = _filled()

    result = asyncio.run(store.list())

    assert [i.trace_id for i in result] == ["t4", "t3", "t2", "t1"]


def test_list_filters_by_rule_and_agent() -> None:
    store = _filled()

    by_rule = asyncio.run(store.list(rule="tool_loop"))
    by_agent = asyncio.run(store.list(agent="b"))

    assert [i.trace_id for i in by_rule] == ["t2"]
    assert [i.trace_id for i in by_agent] == ["t4", "t2"]


def test_list_pages_with_a_cursor() -> None:
    store = _filled()

    first = asyncio.run(store.list(limit=2))
    second = asyncio.run(store.list(limit=2, after=order_key(first[-1])))

    assert [i.trace_id for i in first] == ["t4", "t3"]
    assert [i.trace_id for i in second] == ["t2", "t1"]


def test_cursor_does_not_skip_incidents_with_the_same_time() -> None:
    store = InMemoryIncidentStore()
    for trace_id in ("a", "b", "c"):
        asyncio.run(store.save(_at(5, trace_id=trace_id)))

    first = asyncio.run(store.list(limit=2))
    second = asyncio.run(store.list(limit=2, after=order_key(first[-1])))

    seen = [i.trace_id for i in first] + [i.trace_id for i in second]
    assert sorted(seen) == ["a", "b", "c"]


def test_for_trace_returns_every_rule_of_the_trace() -> None:
    store = InMemoryIncidentStore()
    asyncio.run(store.save(_at(1, trace_id="t1", rule="span_error")))
    asyncio.run(store.save(_at(2, trace_id="t1", rule="tool_loop")))
    asyncio.run(store.save(_at(3, trace_id="t2")))

    result = asyncio.run(store.for_trace("t1"))

    assert {i.rule for i in result} == {"span_error", "tool_loop"}
