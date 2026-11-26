"""Worker: turns a time window of spans into incidents."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from rolda.detection import Baseline, Rule
from rolda.incidents import Incident, IncidentStore
from rolda.traces import SpanSource, build_traces


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
