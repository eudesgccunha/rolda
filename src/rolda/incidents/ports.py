"""Ports of the incidents feature."""

from collections.abc import Sequence
from typing import Protocol

from rolda.incidents.labels import Label, LabelSource
from rolda.incidents.model import Incident, OrderKey


class UnknownIncidentError(LookupError):
    """Raised when a label refers to an incident that does not exist."""


class IncidentStore(Protocol):
    """Port that persists incidents."""

    async def save(self, incident: Incident) -> bool:
        """Store an incident unless ``(trace_id, rule)`` already exists.

        Return True when the incident is new.
        """
        ...

    async def list(
        self,
        *,
        rule: str | None = None,
        agent: str | None = None,
        limit: int = 50,
        after: OrderKey | None = None,
    ) -> Sequence[Incident]:
        """Return incidents newest first.

        ``after`` is the ``order_key`` of the last incident of the previous
        page. Only older incidents are returned.
        """
        ...

    async def for_trace(self, trace_id: str) -> Sequence[Incident]:
        """Return every incident of one trace."""
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

    async def for_trace(self, trace_id: str) -> Sequence[Label]:
        """Return the labels of every incident of one trace."""
        ...
