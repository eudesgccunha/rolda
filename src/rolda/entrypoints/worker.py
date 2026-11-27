"""Worker: turns a time window of spans into incidents."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from rolda.alerts import Alert, AlertDeliveryError, Alerter
from rolda.checkpoints import CheckpointStore, Leadership
from rolda.detection import Baseline, Rule, suppress_redundant
from rolda.entrypoints.settings import Settings
from rolda.incidents import (
    AlertOutbox,
    Incident,
    IncidentStore,
    probable_cause,
)
from rolda.incidents.cause import hypothesis_for
from rolda.traces import SpanSource, Trace, build_traces

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    """Window settings.

    ``lag`` re-reads the end of the previous window to catch late spans.
    ``baseline_span`` is the history used by the outlier rules.
    ``baseline_refresh`` is how long a built baseline is reused before the
    history is read again. A failed alert is retried up to
    ``alert_max_attempts`` times, waiting ``alert_backoff`` times the number
    of failures between tries.
    """

    lag: timedelta = timedelta(minutes=2)
    baseline_span: timedelta = timedelta(days=7)
    baseline_refresh: timedelta = timedelta(hours=1)
    alert_max_attempts: int = 5
    alert_backoff: timedelta = timedelta(seconds=30)


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
        outbox: AlertOutbox | None = None,
    ) -> None:
        self._source = source
        self._store = store
        self._rules = rules
        self._config = config
        self._clock = clock
        self._alerters = alerters
        self._outbox = outbox
        self._baseline: Baseline | None = None
        self._baseline_start: datetime | None = None

    async def run_window(self, start: datetime, end: datetime) -> WindowResult:
        """Process ``[start, end)`` plus the lag before it.

        Running the same window again creates no new incidents, because
        the store keeps one incident per trace and rule.
        """
        await self._deliver_pending()
        lag = self._config.lag
        spans = await self._source.spans_between(start - lag, end)
        baseline = await self._baseline_for(start)
        traces = build_traces(spans)
        findings = 0
        new = 0
        for trace in traces:
            for incident, hypothesis in self._incidents_for(trace, baseline):
                findings += 1
                if await self._store.save(incident, self._channel_names()):
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

    def _channel_names(self) -> list[str]:
        """Channels to queue for a new incident. None without an outbox."""
        if self._outbox is None:
            return []
        return [alerter.name for alerter in self._alerters]

    async def _notify(self, alert: Alert) -> None:
        for alerter in self._alerters:
            await self._send(alerter, alert)

    async def _send(self, alerter: Alerter, alert: Alert) -> None:
        incident = alert.incident
        try:
            await alerter.send(alert)
        except AlertDeliveryError:
            logger.exception(
                "alert delivery failed for trace %s", incident.trace_id
            )
            delivered = False
        else:
            delivered = True
        if self._outbox is not None:
            await self._outbox.mark_delivery(
                incident.trace_id,
                incident.rule,
                alerter.name,
                delivered=delivered,
            )

    async def _deliver_pending(self) -> None:
        """Retry alerts that failed before, one channel at a time."""
        if self._outbox is None:
            return
        pending = await self._outbox.pending(
            limit=50,
            max_attempts=self._config.alert_max_attempts,
            backoff=self._config.alert_backoff,
        )
        by_name = {alerter.name: alerter for alerter in self._alerters}
        for delivery in pending:
            incident = delivery.incident
            alerter = by_name.get(delivery.channel)
            if alerter is None:
                # The channel was removed from the configuration. Count the
                # attempt so the delivery is dropped after the maximum.
                await self._outbox.mark_delivery(
                    incident.trace_id,
                    incident.rule,
                    delivery.channel,
                    delivered=False,
                )
                continue
            hypothesis = hypothesis_for(
                incident.rule, incident.path, incident.evidence
            )
            await self._send(alerter, Alert(incident, hypothesis))


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
    *,
    checkpoints: CheckpointStore | None = None,
    leadership: Leadership | None = None,
    stop: asyncio.Event | None = None,
    name: str = "worker",
) -> None:
    """Run contiguous windows until ``stop`` is set or ``iterations`` pass.

    With a checkpoint store the worker resumes where the last one stopped. A
    long outage is capped at ``max_catchup`` and the rest is processed in
    chunks. With a ``leadership`` only the worker that holds the lock works.
    A failed window is logged and retried from the same start.
    """
    state = _LoopState(worker, settings, clock, checkpoints, leadership, name)
    count = 0
    try:
        while (iterations is None or count < iterations) and not (
            stop is not None and stop.is_set()
        ):
            count += 1
            caught_up = await state.step()
            if caught_up:
                await sleep(settings.interval.total_seconds())
    finally:
        if leadership is not None:
            await leadership.release()


class _LoopState:
    """What ``serve`` remembers between iterations."""

    def __init__(
        self,
        worker: WindowRunner,
        settings: Settings,
        clock: Callable[[], datetime],
        checkpoints: CheckpointStore | None,
        leadership: Leadership | None,
        name: str,
    ) -> None:
        self._worker = worker
        self._settings = settings
        self._clock = clock
        self._checkpoints = checkpoints
        self._leadership = leadership
        self._name = name
        self._cursor: datetime | None = None

    async def _leads(self) -> bool:
        if self._leadership is None:
            return True
        if await self._leadership.is_held():
            return True
        self._cursor = None
        acquired = await self._leadership.try_acquire(self._name)
        if not acquired:
            logger.info("standing by: another worker holds the lock")
        return acquired

    async def _start(self, end: datetime) -> datetime:
        if self._cursor is None and self._checkpoints is not None:
            self._cursor = await self._checkpoints.get(self._name)
        start = self._cursor or end - self._settings.window
        oldest = end - self._settings.max_catchup
        if start < oldest:
            logger.warning(
                "skipping %s of unprocessed spans: the worker was down "
                "longer than ROLDA_MAX_CATCHUP_SECONDS",
                oldest - start,
            )
            start = oldest
        return start

    async def step(self) -> bool:
        """Process one chunk. Return True when there is nothing left to do."""
        try:
            if not await self._leads():
                return True
            end = self._clock()
            start = await self._start(end)
            chunk_end = min(end, start + self._settings.chunk)
            # A failure below keeps this start, so the same window is retried.
            self._cursor = start
            result = await self._worker.run_window(start, chunk_end)
            if self._checkpoints is not None:
                await self._checkpoints.set(self._name, chunk_end)
            self._cursor = chunk_end
        except Exception:
            logger.exception("window failed; retrying from the same start")
            return True
        logger.info(
            "window %s..%s traces=%d findings=%d new_incidents=%d",
            start.isoformat(),
            chunk_end.isoformat(),
            result.traces,
            result.findings,
            result.new_incidents,
        )
        return chunk_end >= end
