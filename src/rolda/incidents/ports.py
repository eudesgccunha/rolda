"""Ports of the incidents feature."""

from typing import Protocol

from rolda.incidents.model import Incident


class IncidentStore(Protocol):
    """Port that persists incidents."""

    async def save(self, incident: Incident) -> bool:
        """Store an incident unless ``(trace_id, rule)`` already exists.

        Return True when the incident is new.
        """
        ...
