"""Alert domain model and port."""

from dataclasses import dataclass
from typing import Protocol

from rolda.incidents import Incident


class AlertDeliveryError(Exception):
    """Raised by an alerter when an alert could not be delivered."""


@dataclass(frozen=True, slots=True)
class Alert:
    """A new incident plus the probable cause shown to a human."""

    incident: Incident
    hypothesis: str


class Alerter(Protocol):
    """Port implemented by every alert channel."""

    async def send(self, alert: Alert) -> None:
        """Deliver an alert. Raise ``AlertDeliveryError`` on failure."""
        ...
