"""In-memory ``IncidentStore`` for tests and local runs."""

from rolda.incidents.model import Incident


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
