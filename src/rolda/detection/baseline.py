"""Per-agent history used by the outlier rules."""

import math
from array import array
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from rolda.detection.stats import Stats
from rolda.traces import Operation, Span, Trace

TIMED_OPERATIONS = frozenset({Operation.LLM, Operation.TOOL})


def span_key(agent: str, span: Span) -> str:
    """Return the group a span is compared with: agent, kind and name."""
    return f"{agent}|{span.operation.value}|{span.tool_name or span.name}"


def span_tokens(span: Span) -> int | None:
    """Return the tokens of one LLM span, or None if none were reported."""
    if span.operation is not Operation.LLM:
        return None
    counts = [
        c for c in (span.input_tokens, span.output_tokens) if c is not None
    ]
    return sum(counts) if counts else None


def trace_duration_ns(trace: Trace) -> int:
    """Return the duration of the trace root."""
    return trace.root.duration_ns


def trace_tokens(trace: Trace) -> int | None:
    """Return total LLM tokens in the trace, or None if none reported."""
    total = 0
    seen = False
    for span in trace.spans:
        if span.operation is not Operation.LLM:
            continue
        for count in (span.input_tokens, span.output_tokens):
            if count is not None:
                total += count
                seen = True
    return total if seen else None


def log_scale(value: float) -> float:
    """Return the natural log used for skewed values, never below 0."""
    return math.log(max(value, 1.0))


class BaselineSamples:
    """Compact samples of one slice of history, ready to be merged.

    Each value is one 8 byte float, so a slice of history costs a few bytes
    per span instead of a whole ``Span`` object. Durations and tokens of
    single spans are stored on the log scale, which is how the span rules
    compare them.
    """

    def __init__(self) -> None:
        self.durations: dict[str, array[float]] = {}
        self.tokens: dict[str, array[float]] = {}
        self.span_durations: dict[str, array[float]] = {}
        self.span_tokens: dict[str, array[float]] = {}
        self.trace_count = 0

    @staticmethod
    def _add(groups: dict[str, array[float]], key: str, value: float) -> None:
        group = groups.get(key)
        if group is None:
            group = groups[key] = array("d")
        group.append(value)

    def add_traces(self, traces: Iterable[Trace]) -> None:
        """Record what each trace says about its agent and its spans."""
        for trace in traces:
            agent = trace.root.agent
            # A trace cut by the edge of a slice has no root span. Its first
            # span would stand in for the whole trace, so leave it out.
            if agent is None or not any(
                span.parent_span_id is None for span in trace.spans
            ):
                continue
            self.trace_count += 1
            self._add(self.durations, agent, float(trace_duration_ns(trace)))
            total = trace_tokens(trace)
            if total is not None:
                self._add(self.tokens, agent, float(total))
            for span in trace.spans:
                key = span_key(agent, span)
                if span.operation in TIMED_OPERATIONS:
                    self._add(
                        self.span_durations,
                        key,
                        log_scale(float(span.duration_ns)),
                    )
                used = span_tokens(span)
                if used is not None:
                    self._add(self.span_tokens, key, log_scale(float(used)))


def _summarize(
    parts: list[dict[str, array[float]]],
) -> dict[str, Stats]:
    merged: dict[str, array[float]] = {}
    for part in parts:
        for key, values in part.items():
            group = merged.get(key)
            if group is None:
                group = merged[key] = array("d")
            group.extend(values)
    return {key: Stats.from_samples(values) for key, values in merged.items()}


@dataclass(frozen=True, slots=True)
class Baseline:
    """What the outlier rules know about normal behavior, as statistics.

    Groups are keyed by agent (trace level) or by agent, kind and name (span
    level). The span groups are on the log scale.
    """

    durations: Mapping[str, Stats]
    tokens: Mapping[str, Stats]
    span_durations: Mapping[str, Stats] = field(default_factory=dict)
    span_tokens: Mapping[str, Stats] = field(default_factory=dict)

    @classmethod
    def from_samples(cls, parts: Iterable[BaselineSamples]) -> "Baseline":
        """Merge slices of history into one baseline."""
        slices = list(parts)
        return cls(
            durations=_summarize([p.durations for p in slices]),
            tokens=_summarize([p.tokens for p in slices]),
            span_durations=_summarize([p.span_durations for p in slices]),
            span_tokens=_summarize([p.span_tokens for p in slices]),
        )

    @classmethod
    def from_traces(cls, traces: Iterable[Trace]) -> "Baseline":
        """Build a baseline from historical traces."""
        samples = BaselineSamples()
        samples.add_traces(traces)
        return cls.from_samples([samples])
