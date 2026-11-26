"""Ports of the incidents feature."""

from collections.abc import Sequence
from typing import Protocol

from rolda.incidents.labels import Label, LabelSource
from rolda.incidents.model import Incident


class UnknownIncidentError(LookupError):
    """Raised when a label refers to an incident that does not exist."""


class IncidentStore(Protocol):
    """Port that persists incidents."""

    async def save(self, incident: Incident) -> bool:
        """Store an incident unless ``(trace_id, rule)`` already exists.

        Return True when the incident is new.
        """
        ...


class LabelStore(Protocol):
    """Port that persists labels."""

    async def upsert(self, label: Label) -> None:
        """Store a label, replacing the one with the same key.

        Raise ``UnknownIncidentError`` if the incident does not exist.
        """
        ...

    async def labeled(
        self, source: LabelSource
    ) -> Sequence[tuple[Incident, Label]]:
        """Return labeled incidents from one source, oldest label first."""
        ...
