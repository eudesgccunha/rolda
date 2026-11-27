"""Deterministic detection rules (vela)."""

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from rolda.detection.baseline import (
    TIMED_OPERATIONS,
    Baseline,
    span_key,
    trace_duration_ns,
    trace_tokens,
)
from rolda.detection.model import Confidence, Finding
from rolda.detection.stats import robust_z
from rolda.traces import Operation, Span, SpanStatus, Trace


@dataclass(frozen=True, slots=True)
class DetectionConfig:
    """Thresholds, calibrated on simulated runs (ADR 0009).

    Re-check them with real, human-labeled traces.
    """

    tool_loop_repeats: int = 3
    z_threshold: float = 3.5
    min_samples: int = 30
    latency_z: float | None = None
    span_latency_z: float | None = 3.0
    token_z: float | None = 2.5

    def z_for(self, rule: str) -> float:
        """Return the z-score threshold of a rule, or the shared value."""
        override = {
            "latency_outlier": self.latency_z,
            "span_latency_outlier": self.span_latency_z,
            "token_outlier": self.token_z,
        }.get(rule)
        return self.z_threshold if override is None else override


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
    if score is None or score <= config.z_for(rule):
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


def _log(value: float) -> float:
    return math.log(max(value, 1.0))


class SpanLatencyOutlier:
    """Flag the model or tool call that was much slower than usual.

    Each span is compared with spans of the same agent, kind and name.
    Durations are skewed to the right, so the score uses their logarithm.
    """

    name = "span_latency_outlier"

    def __init__(self, config: DetectionConfig) -> None:
        self._config = config

    def evaluate(self, trace: Trace, baseline: Baseline) -> Sequence[Finding]:
        """Report the slowest outlying span of the trace, if any."""
        agent = trace.root.agent
        if agent is None:
            return ()
        worst: tuple[float, Span] | None = None
        for span in trace.spans:
            if span.operation not in TIMED_OPERATIONS:
                continue
            history = baseline.span_durations.get(span_key(agent, span), ())
            if len(history) < self._config.min_samples:
                continue
            score = robust_z(
                _log(float(span.duration_ns)), [_log(h) for h in history]
            )
            if score is None or score <= self._config.z_for(self.name):
                continue
            if worst is None or score > worst[0]:
                worst = (score, span)
        if worst is None:
            return ()
        score, span = worst
        return (
            Finding(
                trace_id=trace.trace_id,
                rule=self.name,
                span_id=span.span_id,
                evidence=(
                    f"span '{span.name}' took "
                    f"{span.duration_ns / 1_000_000:.0f} ms, "
                    f"robust z-score {score:.1f} (log scale)"
                ),
            ),
        )


def default_rules(config: DetectionConfig) -> list[Rule]:
    """Return the MVP rules in a fixed order."""
    return [
        SpanError(),
        ToolLoop(config),
        LatencyOutlier(config),
        SpanLatencyOutlier(config),
        TokenOutlier(config),
    ]
