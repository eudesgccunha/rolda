"""Tests for the alert outbox kept by the in-memory incident store."""

import asyncio
from datetime import UTC, datetime, timedelta

from rolda.detection import Confidence
from rolda.incidents import Incident, InMemoryIncidentStore

T0 = datetime(2026, 11, 26, 10, 0, tzinfo=UTC)


class _Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def _incident(trace_id: str = "t1", rule: str = "span_error") -> Incident:
    return Incident(
        trace_id=trace_id,
        rule=rule,
        span_id="s1",
        evidence="boom",
        confidence=Confidence.HIGH,
        signature="a|span_error|tool|boom",
        path=("root", "tool"),
        detected_at=T0,
    )


def _pending(
    store: InMemoryIncidentStore, max_attempts: int = 3
) -> list[tuple[str, str]]:
    found = asyncio.run(
        store.pending(
            limit=10,
            max_attempts=max_attempts,
            backoff=timedelta(seconds=30),
        )
    )
    return [(d.incident.trace_id, d.channel) for d in found]


def test_a_new_incident_queues_one_delivery_per_channel() -> None:
    store = InMemoryIncidentStore()

    asyncio.run(store.save(_incident(), channels=["slack", "teams"]))

    assert sorted(_pending(store)) == [("t1", "slack"), ("t1", "teams")]


def test_a_duplicate_incident_queues_nothing_more() -> None:
    store = InMemoryIncidentStore()
    asyncio.run(store.save(_incident(), channels=["slack"]))
    asyncio.run(
        store.mark_delivery("t1", "span_error", "slack", delivered=True)
    )

    again = asyncio.run(store.save(_incident(), channels=["slack"]))

    assert again is False
    assert _pending(store) == []


def test_a_delivered_alert_is_not_pending() -> None:
    store = InMemoryIncidentStore()
    asyncio.run(store.save(_incident(), channels=["slack", "teams"]))

    asyncio.run(
        store.mark_delivery("t1", "span_error", "slack", delivered=True)
    )

    assert _pending(store) == [("t1", "teams")]


def test_a_failed_delivery_waits_before_it_is_retried() -> None:
    clock = _Clock()
    store = InMemoryIncidentStore(clock=clock)
    asyncio.run(store.save(_incident(), channels=["slack"]))

    asyncio.run(
        store.mark_delivery("t1", "span_error", "slack", delivered=False)
    )
    assert _pending(store) == []

    clock.now = T0 + timedelta(seconds=31)
    assert _pending(store) == [("t1", "slack")]


def test_a_delivery_gives_up_after_the_maximum_attempts() -> None:
    clock = _Clock()
    store = InMemoryIncidentStore(clock=clock)
    asyncio.run(store.save(_incident(), channels=["slack"]))

    for _ in range(3):
        asyncio.run(
            store.mark_delivery("t1", "span_error", "slack", delivered=False)
        )
        clock.now += timedelta(hours=1)

    assert _pending(store, max_attempts=3) == []


def test_without_channels_nothing_is_queued() -> None:
    store = InMemoryIncidentStore()

    asyncio.run(store.save(_incident()))

    assert _pending(store) == []
