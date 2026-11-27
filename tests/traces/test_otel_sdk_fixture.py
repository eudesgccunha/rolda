"""Tests against traces produced by the real OpenTelemetry SDK."""

import json
from collections import Counter
from pathlib import Path

import pytest

from rolda.traces import (
    Operation,
    SpanStatus,
    Trace,
    build_traces,
    normalize_span,
)

FIXTURE = Path(__file__).parent / "fixtures" / "spans_otel_sdk.json"


@pytest.fixture(scope="module")
def traces() -> list[Trace]:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return build_traces(normalize_span(row) for row in rows)


def test_all_rows_normalize_into_eight_traces(
    traces: list[Trace],
) -> None:
    assert len(traces) == 8
    assert sum(len(trace.spans) for trace in traces) == 42


def test_every_trace_has_an_agent_root(traces: list[Trace]) -> None:
    for trace in traces:
        assert trace.root.operation is Operation.AGENT
        assert trace.root.parent_span_id is None


def test_tool_loop_trace_repeats_the_same_call(
    traces: list[Trace],
) -> None:
    calls = [
        Counter(
            (span.tool_name, span.tool_arguments)
            for span in trace.spans
            if span.operation is Operation.TOOL
        )
        for trace in traces
    ]

    assert max(count for c in calls for count in c.values()) >= 3


def test_error_trace_has_a_failed_tool_span(traces: list[Trace]) -> None:
    failed = [
        span
        for trace in traces
        for span in trace.spans
        if span.operation is Operation.TOOL and span.status is SpanStatus.ERROR
    ]

    assert len(failed) == 1
    assert failed[0].status_message


def test_agents_and_token_counts_are_present(
    traces: list[Trace],
) -> None:
    spans = [span for trace in traces for span in trace.spans]

    assert {span.agent for span in spans} >= {"support-agent", "billing-agent"}
    llm = [s for s in spans if s.operation is Operation.LLM]
    assert all(s.input_tokens is not None for s in llm)
    assert max(s.input_tokens or 0 for s in llm) > 90_000
