"""Traces: domain model, ports and OpenTelemetry normalization."""

from rolda.traces.model import (
    Operation,
    Span,
    SpanStatus,
    Trace,
    build_traces,
)
from rolda.traces.normalize import NormalizationError, normalize_span
from rolda.traces.ports import SpanSource

__all__ = [
    "NormalizationError",
    "Operation",
    "Span",
    "SpanSource",
    "SpanStatus",
    "Trace",
    "build_traces",
    "normalize_span",
]
