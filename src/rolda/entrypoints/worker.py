"""Worker: turns a time window of spans into incidents."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from rolda.alerts import Alert, AlertDeliveryError, Alerter
from rolda.detection import Baseline, Rule, suppress_redundant
from rolda.entrypoints.settings import Settings
from rolda.incidents import (
    Incident,
    IncidentStore,
    probable_cause,
)
from rolda.traces import SpanSource, Trace, build_traces

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    """Window settings.

    ``lag`` re-reads the end of the previous window to catch late spans.
    ``baseline_span`` is the history used by the outlier rules.
    ``baseline_refresh`` is how long a built baseline is reused before the
    history is read again.
    """

    lag: timedelta = timedelta(minutes=2)
    baseline_span: timedelta = timedelta(days=7)
    baseline_refresh: timedelta = timedelta(hours=1)


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
        alerters: Sequence[Alerter] = (),
    ) -> None:
        self._source = source
        self._store = store
        self._rules = rules
        self._config = config
        self._clock = clock
        self._alerters = alerters
        self._baseline: Baseline | None = None
        self._baseline_start: datetime | None = None

    async def run_window(self, start: datetime, end: datetime) -> WindowResult:
        """Process ``[start, end)`` plus the lag before it.

        Running the same window again creates no new incidents, because
        the store keeps one incident per trace and rule.
        """
        lag = self._config.lag
        spans = await self._source.spans_between(start - lag, end)
        baseline = await self._baseline_for(start)
        traces = build_traces(spans)
        findings = 0
        new = 0
        for trace in traces:
            for incident, hypothesis in self._incidents_for(trace, baseline):
                findings += 1
                if await self._store.save(incident):
                    new += 1
                    await self._notify(Alert(incident, hypothesis))
        return WindowResult(
            traces=len(traces), findings=findings, new_incidents=new
        )

    async def _baseline_for(self, start: datetime) -> Baseline:
        """Return the cached baseline, rebuilding it when it is stale."""
        cached = self._baseline
        built_at = self._baseline_start
        if (
            cached is not None
            and built_at is not None
            and timedelta(0)
            <= start - built_at
            < self._config.baseline_refresh
        ):
            return cached
        history = await self._source.spans_between(
            start - self._config.baseline_span, start - self._config.lag
        )
        self._baseline = Baseline.from_traces(build_traces(history))
        self._baseline_start = start
        return self._baseline

    def _incidents_for(
        self, trace: Trace, baseline: Baseline
    ) -> Iterator[tuple[Incident, str]]:
        findings = suppress_redundant(
            [
                finding
                for rule in self._rules
                for finding in rule.evaluate(trace, baseline)
            ]
        )
        for finding in findings:
            cause = probable_cause(trace, finding)
            incident = Incident(
                trace_id=finding.trace_id,
                rule=finding.rule,
                span_id=finding.span_id,
                evidence=finding.evidence,
                confidence=finding.confidence,
                signature=cause.signature,
                path=cause.path,
                detected_at=self._clock(),
            )
            yield incident, cause.hypothesis

    async def _notify(self, alert: Alert) -> None:
        for alerter in self._alerters:
            try:
                await alerter.send(alert)
            except AlertDeliveryError:
                logger.exception(
                    "alert delivery failed for trace %s",
                    alert.incident.trace_id,
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
