"""Per-agent history used by the outlier rules."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from rolda.traces import Operation, Trace


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

    @classmethod
    def from_traces(cls, traces: Iterable[Trace]) -> "Baseline":
        """Build a baseline from historical traces."""
        durations: dict[str, list[float]] = defaultdict(list)
        tokens: dict[str, list[float]] = defaultdict(list)
        for trace in traces:
            agent = trace.root.agent
            if agent is None:
                continue
            durations[agent].append(float(trace_duration_ns(trace)))
            total = trace_tokens(trace)
            if total is not None:
                tokens[agent].append(float(total))
        return cls(
            durations={k: tuple(v) for k, v in durations.items()},
            tokens={k: tuple(v) for k, v in tokens.items()},
        )
