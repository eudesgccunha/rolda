"""Tests for splitting traces between workers by trace id."""

import asyncio
import zlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from rolda.traces import InMemorySpanSource, Shard, Span

SpanFactory = Callable[..., Span]
T0 = datetime(2026, 11, 26, 10, tzinfo=UTC)


def _ids(count: int) -> list[str]:
    return [f"{n:032x}" for n in range(count)]


def test_one_shard_owns_every_trace() -> None:
    shard = Shard.single()

    assert all(shard.owns(t) for t in _ids(100))


def test_every_trace_belongs_to_exactly_one_shard() -> None:
    shards = [Shard(count=3, index=i) for i in range(3)]

    for trace_id in _ids(500):
        owners = [s.index for s in shards if s.owns(trace_id)]
        assert len(owners) == 1


def test_the_split_follows_the_documented_crc32_rule() -> None:
    # ClickHouse has the same CRC32, so the database can filter by shard.
    shard = Shard(count=4, index=2)

    for trace_id in _ids(200):
        expected = zlib.crc32(trace_id.encode()) % 4 == 2
        assert shard.owns(trace_id) is expected


def test_the_split_is_roughly_even() -> None:
    counts = [0, 0, 0]
    for trace_id in _ids(3000):
        for i in range(3):
            counts[i] += Shard(3, i).owns(trace_id)

    assert all(800 < c < 1200 for c in counts), counts


@pytest.mark.parametrize(
    ("count", "index"), [(0, 0), (-1, 0), (3, 3), (3, -1)]
)
def test_an_invalid_shard_is_refused(count: int, index: int) -> None:
    with pytest.raises(ValueError, match="shard"):
        Shard(count=count, index=index)


def test_a_source_returns_only_the_traces_of_its_shard(
    make_span: SpanFactory,
) -> None:
    spans = [make_span("root", trace_id=t) for t in _ids(60)]
    parts = [InMemorySpanSource(spans, shard=Shard(3, i)) for i in range(3)]

    got = [
        asyncio.run(p.spans_between(T0, T0 + timedelta(minutes=1)))
        for p in parts
    ]

    seen = [s.trace_id for part in got for s in part]
    assert sorted(seen) == sorted(_ids(60))
    assert all(len(part) > 5 for part in got)
