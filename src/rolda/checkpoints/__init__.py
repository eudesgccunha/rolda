"""Worker progress and leadership: where to resume, and who is the worker."""

from datetime import datetime
from typing import Protocol


class CheckpointStore(Protocol):
    """Port that remembers how far the worker has processed."""

    async def get(self, name: str) -> datetime | None:
        """Return the saved cursor, or None if there is none."""
        ...

    async def set(self, name: str, value: datetime) -> None:
        """Save the cursor."""
        ...


class Leadership(Protocol):
    """Port that lets one worker at a time do the work."""

    async def try_acquire(self, name: str) -> bool:
        """Take the lock without waiting. Return True if this worker leads."""
        ...

    async def is_held(self) -> bool:
        """Return True while this worker still holds the lock."""
        ...

    async def release(self) -> None:
        """Give the lock back."""
        ...


class InMemoryCheckpointStore:
    """Keep cursors in a dict, for tests and single-process runs."""

    def __init__(self) -> None:
        self._values: dict[str, datetime] = {}

    async def get(self, name: str) -> datetime | None:
        """Return the saved cursor, or None if there is none."""
        return self._values.get(name)

    async def set(self, name: str, value: datetime) -> None:
        """Save the cursor."""
        self._values[name] = value


__all__ = [
    "CheckpointStore",
    "InMemoryCheckpointStore",
    "Leadership",
]
