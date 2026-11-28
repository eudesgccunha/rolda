"""Keep the baseline up to date by reading history in slices.

The history is read in short time slices. Only a few floats per span are kept
for each slice, and a refresh reads just the slices it does not have yet, so
memory stays small and an hourly refresh costs about an hour of spans, not
seven days.
"""

from datetime import UTC, datetime, timedelta

from rolda.detection.baseline import Baseline, BaselineSamples
from rolda.traces import SpanSource, build_traces


def _floor(moment: datetime, size: timedelta) -> datetime:
    step = int(size.total_seconds())
    return datetime.fromtimestamp(
        (int(moment.timestamp()) // step) * step, UTC
    )


class BaselineHistory:
    """Mergeable samples of the last ``span`` of history, slice by slice."""

    def __init__(
        self,
        source: SpanSource,
        *,
        span: timedelta,
        slice_size: timedelta,
        lag: timedelta,
    ) -> None:
        self._source = source
        self._span = span
        self._size = slice_size
        self._lag = lag
        self._slices: dict[datetime, BaselineSamples] = {}

    @property
    def trace_count(self) -> int:
        """Traces summarized in the slices kept so far."""
        return sum(s.trace_count for s in self._slices.values())

    async def refresh(self, start: datetime) -> Baseline:
        """Read the missing slices and return the baseline they give.

        Only complete slices that end at least ``lag`` before ``start`` are
        used, so late spans have had time to arrive. Slices read before an
        error are kept, so a retry continues where it stopped.
        """
        end = _floor(start - self._lag, self._size)
        first = end - self._span
        for key in [k for k in self._slices if k < first]:
            del self._slices[key]
        count = int(self._span / self._size)
        for index in range(count):
            slice_start = end - self._size * (index + 1)
            if slice_start in self._slices:
                continue
            spans = await self._source.spans_between(
                slice_start, slice_start + self._size
            )
            samples = BaselineSamples()
            samples.add_traces(build_traces(spans))
            self._slices[slice_start] = samples
        return Baseline.from_samples(self._slices.values())
