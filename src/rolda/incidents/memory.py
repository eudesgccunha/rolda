"""In-memory ``IncidentStore`` for tests and local runs."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from rolda.incidents.labels import Label, LabelSource
from rolda.incidents.model import (
    Incident,
    OrderKey,
    PendingDelivery,
    agent_of,
    order_key,
)
from rolda.incidents.ports import UnknownIncidentError


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class _Delivery:
    attempts: int = 0
    delivered: bool = False
    last_attempt: datetime | None = None


class InMemoryIncidentStore:
    """Keep incidents in a dict keyed by ``(trace_id, rule)``.

    It also keeps the alert outbox, like the PostgreSQL store does.
    """

    def __init__(self, clock: Callable[[], datetime] = _utc_now) -> None:
        self._items: dict[tuple[str, str], Incident] = {}
        self._deliveries: dict[tuple[str, str, str], _Delivery] = {}
        self._clock = clock

    async def save(
        self, incident: Incident, channels: Sequence[str] = ()
    ) -> bool:
        """Store the incident if its key is new, and queue its alerts."""
        key = (incident.trace_id, incident.rule)
        if key in self._items:
            return False
        self._items[key] = incident
        for channel in channels:
            self._deliveries[(*key, channel)] = _Delivery()
        return True

    async def pending(
        self, *, limit: int, max_attempts: int, backoff: timedelta
    ) -> Sequence[PendingDelivery]:
        """Return deliveries that are due for another attempt."""
        now = self._clock()
        due: list[PendingDelivery] = []
        for (trace_id, rule, channel), delivery in self._deliveries.items():
            if delivery.delivered or delivery.attempts >= max_attempts:
                continue
            if (
                delivery.last_attempt is not None
                and now < delivery.last_attempt + backoff * delivery.attempts
            ):
                continue
            incident = self._items[(trace_id, rule)]
            due.append(PendingDelivery(incident, channel, delivery.attempts))
        return due[:limit]

    async def mark_delivery(
        self, trace_id: str, rule: str, channel: str, *, delivered: bool
    ) -> None:
        """Record the result of one attempt."""
        delivery = self._deliveries[(trace_id, rule, channel)]
        delivery.attempts += 1
        delivery.last_attempt = self._clock()
        delivery.delivered = delivered

    def all(self) -> list[Incident]:
        """Return stored incidents in insertion order."""
        return list(self._items.values())

    async def list(
        self,
        *,
        rule: str | None = None,
        agent: str | None = None,
        limit: int = 50,
        after: OrderKey | None = None,
    ) -> Sequence[Incident]:
        """Return incidents newest first, with filters and a cursor."""
        found = [
            i
            for i in self._items.values()
            if (rule is None or i.rule == rule)
            and (agent is None or agent_of(i) == agent)
            and (after is None or order_key(i) < after)
        ]
        found.sort(key=order_key, reverse=True)
        return found[:limit]

    async def for_trace(self, trace_id: str) -> Sequence[Incident]:
        """Return every incident of one trace."""
        return [i for i in self._items.values() if i.trace_id == trace_id]


class InMemoryLabelStore:
    """Keep labels keyed by ``(trace_id, rule, source)``."""

    def __init__(self, incidents: InMemoryIncidentStore) -> None:
        self._incidents = incidents
        self._labels: dict[tuple[str, str, LabelSource], Label] = {}

    async def upsert(self, label: Label) -> None:
        """Store or replace a label for an existing incident."""
        known = {(i.trace_id, i.rule) for i in self._incidents.all()}
        if (label.trace_id, label.rule) not in known:
            msg = f"no incident for trace {label.trace_id} rule {label.rule}"
            raise UnknownIncidentError(msg)
        self._labels[(label.trace_id, label.rule, label.source)] = label

    async def for_trace(self, trace_id: str) -> Sequence[Label]:
        """Return the labels of every incident of one trace."""
        return [
            label
            for label in self._labels.values()
            if label.trace_id == trace_id
        ]

    async def labeled(
        self, source: LabelSource
    ) -> Sequence[tuple[Incident, Label]]:
        """Return labeled incidents from one source."""
        by_key = {(i.trace_id, i.rule): i for i in self._incidents.all()}
        found = [
            (by_key[(label.trace_id, label.rule)], label)
            for label in self._labels.values()
            if label.source is source
        ]
        return sorted(found, key=lambda pair: pair[1].labeled_at)
