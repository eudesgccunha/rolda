"""Split the traces between workers by trace id."""

import zlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Shard:
    """One worker's share of the traces: ``crc32(trace_id) % count == index``.

    CRC32 is the same in Python (``zlib.crc32``) and in ClickHouse
    (``CRC32``), so the database can filter by shard, and a trace always
    lands on the same worker.
    """

    count: int = 1
    index: int = 0

    def __post_init__(self) -> None:
        if self.count < 1 or not 0 <= self.index < self.count:
            msg = f"invalid shard {self.index} of {self.count}"
            raise ValueError(msg)

    @classmethod
    def single(cls) -> "Shard":
        """The shard that owns everything."""
        return cls(1, 0)

    def owns(self, trace_id: str) -> bool:
        """Return True if this shard is responsible for the trace."""
        return zlib.crc32(trace_id.encode()) % self.count == self.index
