"""Worker: turns a time window of spans into incidents."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from rolda.detection import Baseline, Rule
from rolda.entrypoints.settings import Settings
from rolda.incidents import Incident, IncidentStore
from rolda.traces import SpanSource, build_traces

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    """Window settings.

    ``lag`` re-reads the end of the previous window to catch late spans.
    ``baseline_span`` is the history used by the outlier rules.
    """

    lag: timedelta = timedelta(minutes=2)
    baseline_span: timedelta = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class WindowResult:
    """What one window run did."""

    traces: int
    findings: int
    new_incidents: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Worker:
    """Run the rules over a window and store incidents idempotently."""

    def __init__(
        self,
        source: SpanSource,
        store: IncidentStore,
        rules: Sequence[Rule],
        config: WorkerConfig,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._source = source
        self._store = store
        self._rules = rules
        self._config = config
        self._clock = clock

    async def run_window(self, start: datetime, end: datetime) -> WindowResult:
        """Process ``[start, end)`` plus the lag before it.

        Running the same window again creates no new incidents, because
        the store keeps one incident per trace and rule.
        """
        lag = self._config.lag
        spans = await self._source.spans_between(start - lag, end)
        history = await self._source.spans_between(
            start - self._config.baseline_span, start - lag
        )
        baseline = Baseline.from_traces(build_traces(history))
        traces = build_traces(spans)
        findings = 0
        new = 0
        for trace in traces:
            for rule in self._rules:
                for finding in rule.evaluate(trace, baseline):
                    findings += 1
                    incident = Incident(
                        trace_id=finding.trace_id,
                        rule=finding.rule,
                        span_id=finding.span_id,
                        evidence=finding.evidence,
                        confidence=finding.confidence,
                        detected_at=self._clock(),
                    )
                    new += await self._store.save(incident)
        return WindowResult(
            traces=len(traces), findings=findings, new_incidents=new
        )


class WindowRunner(Protocol):
    """Anything that can process a window."""

    async def run_window(self, start: datetime, end: datetime) -> WindowResult:
        """Process ``[start, end)``."""
        ...


async def serve(
    worker: WindowRunner,
    settings: Settings,
    clock: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    iterations: int | None = None,
) -> None:
    """Run contiguous windows forever, or ``iterations`` times."""
    previous_end: datetime | None = None
    count = 0
    while iterations is None or count < iterations:
        end = clock()
        start = previous_end or end - settings.window
        result = await worker.run_window(start, end)
        logger.info(
            "window %s..%s traces=%d findings=%d new_incidents=%d",
            start.isoformat(),
            end.isoformat(),
            result.traces,
            result.findings,
            result.new_incidents,
        )
        previous_end = end
        count += 1
        await sleep(settings.interval.total_seconds())
