"""In-memory ``IncidentStore`` for tests and local runs."""

from collections.abc import Sequence

from rolda.incidents.labels import Label, LabelSource
from rolda.incidents.model import Incident
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
