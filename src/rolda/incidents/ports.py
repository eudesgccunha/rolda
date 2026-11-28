"""Ports of the incidents feature."""

from collections.abc import Sequence
from datetime import timedelta
from typing import Protocol

from rolda.incidents.labels import Label, LabelSource
from rolda.incidents.model import Incident, OrderKey, PendingDelivery


class UnknownIncidentError(LookupError):
    """Raised when a label refers to an incident that does not exist."""


class IncidentStore(Protocol):
    """Port that persists incidents."""

    async def save(
        self, incident: Incident, channels: Sequence[str] = ()
    ) -> bool:
        """Store an incident unless ``(trace_id, rule)`` already exists.

        Return True when the incident is new. For a new incident the store
        also queues one alert delivery per channel, in the same step, so an
        incident is never saved without its alerts being queued.
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


class AlertOutbox(Protocol):
    """Port that remembers which alerts still have to be delivered."""

    async def pending(
        self, *, limit: int, max_attempts: int, backoff: timedelta
    ) -> Sequence[PendingDelivery]:
        """Return deliveries to retry.

        A delivery that failed ``n`` times waits ``n * backoff`` before the
        next try, and is dropped after ``max_attempts`` failures.
        """
        ...

    async def mark_delivery(
        self, trace_id: str, rule: str, channel: str, *, delivered: bool
    ) -> None:
        """Record the result of one attempt."""
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
