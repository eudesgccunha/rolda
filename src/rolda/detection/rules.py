"""Deterministic detection rules (vela)."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from rolda.detection.baseline import (
    Baseline,
    trace_duration_ns,
    trace_tokens,
)
from rolda.detection.model import Confidence, Finding
from rolda.detection.stats import robust_z
from rolda.traces import Operation, Span, SpanStatus, Trace


@dataclass(frozen=True, slots=True)
class DetectionConfig:
    """Starting thresholds. Calibrate them with real data."""

    tool_loop_repeats: int = 3
    z_threshold: float = 3.5
    min_samples: int = 30


class Rule(Protocol):
    """Port implemented by every detection rule."""

    name: str

    def evaluate(self, trace: Trace, baseline: Baseline) -> Sequence[Finding]:
        """Return findings for one trace."""
        ...


class SpanError:
    """Flag the span where an error started."""

    name = "span_error"

    def evaluate(self, trace: Trace, baseline: Baseline) -> Sequence[Finding]:
        """Report the earliest error span with no failing child."""
        del baseline
        for span in trace.spans:
            if span.status is not SpanStatus.ERROR:
                continue
            if any(
                child.status is SpanStatus.ERROR
                for child in trace.children(span.span_id)
            ):
                continue
            detail = span.status_message or "no message"
            return (
                Finding(
                    trace_id=trace.trace_id,
                    rule=self.name,
                    span_id=span.span_id,
                    evidence=f"span '{span.name}' failed: {detail}",
                ),
            )
        return ()


class ToolLoop:
    """Flag the same tool called repeatedly with the same arguments."""

    name = "tool_loop"

    def __init__(self, config: DetectionConfig) -> None:
        self._repeats = config.tool_loop_repeats

    def evaluate(self, trace: Trace, baseline: Baseline) -> Sequence[Finding]:
        """Report the most repeated tool call, if above the limit."""
        del baseline
        calls = [
            span
            for span in trace.spans
            if span.operation is Operation.TOOL and span.tool_name
        ]
        counts = Counter((s.tool_name, s.tool_arguments) for s in calls)
        if not counts:
            return ()
        ((key, count),) = counts.most_common(1)
        if count < self._repeats:
            return ()
        first = next(
            s for s in calls if (s.tool_name, s.tool_arguments) == key
        )
        has_args = first.tool_arguments is not None
        suffix = (
            "with the same arguments"
            if has_args
            else "(arguments not captured)"
        )
        return (
            Finding(
                trace_id=trace.trace_id,
                rule=self.name,
                span_id=first.span_id,
                evidence=f"{first.tool_name} called {count} times {suffix}",
                confidence=Confidence.HIGH if has_args else Confidence.LOW,
            ),
        )


def _outlier(
    rule: str,
    trace: Trace,
    value: float | None,
    samples: Mapping[str, tuple[float, ...]],
    config: DetectionConfig,
    label: str,
) -> Sequence[Finding]:
    root: Span = trace.root
    history = samples.get(root.agent or "", ())
    if value is None or len(history) < config.min_samples:
        return ()
    score = robust_z(value, history)
    if score is None or score <= config.z_threshold:
        return ()
    return (
        Finding(
            trace_id=trace.trace_id,
            rule=rule,
            span_id=root.span_id,
            evidence=f"{label} {value:.0f} has robust z-score {score:.1f}",
        ),
    )


class LatencyOutlier:
    """Flag a trace much slower than the agent's history."""

    name = "latency_outlier"

    def __init__(self, config: DetectionConfig) -> None:
        self._config = config

    def evaluate(self, trace: Trace, baseline: Baseline) -> Sequence[Finding]:
        """Compare the root duration with the agent baseline."""
        return _outlier(
            self.name,
            trace,
            float(trace_duration_ns(trace)),
            baseline.durations,
            self._config,
            "duration (ns)",
        )


class TokenOutlier:
    """Flag a trace using many more tokens than the agent's history."""

    name = "token_outlier"

    def __init__(self, config: DetectionConfig) -> None:
        self._config = config

    def evaluate(self, trace: Trace, baseline: Baseline) -> Sequence[Finding]:
        """Compare total tokens with the agent baseline."""
        total = trace_tokens(trace)
        return _outlier(
            self.name,
            trace,
            None if total is None else float(total),
            baseline.tokens,
            self._config,
            "tokens",
        )


def default_rules(config: DetectionConfig) -> list[Rule]:
    """Return the MVP rules in a fixed order."""
    return [
        SpanError(),
        ToolLoop(config),
        LatencyOutlier(config),
        TokenOutlier(config),
    ]
