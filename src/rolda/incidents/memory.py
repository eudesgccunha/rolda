"""In-memory ``IncidentStore`` for tests and local runs."""

from collections.abc import Sequence

from rolda.incidents.labels import Label, LabelSource
from rolda.incidents.model import Incident, OrderKey, agent_of, order_key
from rolda.incidents.ports import UnknownIncidentError


class InMemoryIncidentStore:
    """Keep incidents in a dict keyed by ``(trace_id, rule)``."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], Incident] = {}

    async def save(self, incident: Incident) -> bool:
        """Store the incident if its key is new."""
        key = (incident.trace_id, incident.rule)
        if key in self._items:
            return False
        self._items[key] = incident
        return True

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
