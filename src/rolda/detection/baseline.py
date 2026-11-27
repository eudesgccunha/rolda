"""Per-agent history used by the outlier rules."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

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


@dataclass(frozen=True, slots=True)
class Baseline:
    """Duration and token samples per agent."""

    durations: Mapping[str, tuple[float, ...]]
    tokens: Mapping[str, tuple[float, ...]]
    span_durations: Mapping[str, tuple[float, ...]] = field(
        default_factory=dict
    )
    span_tokens: Mapping[str, tuple[float, ...]] = field(default_factory=dict)

    @classmethod
    def from_traces(cls, traces: Iterable[Trace]) -> "Baseline":
        """Build a baseline from historical traces."""
        durations: dict[str, list[float]] = defaultdict(list)
        tokens: dict[str, list[float]] = defaultdict(list)
        spans: dict[str, list[float]] = defaultdict(list)
        span_token_samples: dict[str, list[float]] = defaultdict(list)
        for trace in traces:
            agent = trace.root.agent
            if agent is None:
                continue
            durations[agent].append(float(trace_duration_ns(trace)))
            total = trace_tokens(trace)
            if total is not None:
                tokens[agent].append(float(total))
            for span in trace.spans:
                if span.operation in TIMED_OPERATIONS:
                    spans[span_key(agent, span)].append(
                        float(span.duration_ns)
                    )
                used = span_tokens(span)
                if used is not None:
                    span_token_samples[span_key(agent, span)].append(
                        float(used)
                    )
        return cls(
            durations={k: tuple(v) for k, v in durations.items()},
            tokens={k: tuple(v) for k, v in tokens.items()},
            span_durations={k: tuple(v) for k, v in spans.items()},
            span_tokens={k: tuple(v) for k, v in span_token_samples.items()},
        )
