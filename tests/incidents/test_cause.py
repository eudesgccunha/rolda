"""Tests for the probable cause (SPEC section 5)."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from rolda.detection import Baseline, Finding, SpanError, ToolLoop
from rolda.detection.rules import DetectionConfig
from rolda.incidents.cause import normalize_error, probable_cause
from rolda.traces import (
    Operation,
    Span,
    SpanStatus,
    Trace,
    build_traces,
    normalize_span,
)

SpanFactory = Callable[..., Span]
FIXTURE = (
    Path(__file__).parent.parent
    / "traces"
    / "fixtures"
    / "spans_otel_sdk.json"
)
EMPTY = Baseline.from_traces([])


def _sdk_trace(prefix: str) -> Trace:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    traces = build_traces(normalize_span(row) for row in rows)
    return next(t for t in traces if t.trace_id.startswith(prefix))


def test_path_goes_from_root_to_the_failing_span() -> None:
    trace = _sdk_trace("1aea792b")
    [finding] = SpanError().evaluate(trace, EMPTY)

    cause = probable_cause(trace, finding)

    assert cause.path[0] == trace.root.name
    assert len(cause.path) == 2
    failing = next(s for s in trace.spans if s.span_id == finding.span_id)
    assert cause.path[-1] == failing.name


def test_signature_has_agent_rule_operation_and_error() -> None:
    trace = _sdk_trace("1aea792b")
    [finding] = SpanError().evaluate(trace, EMPTY)

    cause = probable_cause(trace, finding)

    agent, rule, operation, error = cause.signature.split("|")
    assert (agent, rule, operation) == (
        "support-agent",
        "span_error",
        "tool",
    )
    assert error


def test_hypothesis_mentions_path_and_evidence() -> None:
    trace = _sdk_trace("9eea290c")
    [finding] = ToolLoop(DetectionConfig()).evaluate(trace, EMPTY)

    cause = probable_cause(trace, finding)

    assert "search_orders" in cause.hypothesis
    assert " > " in cause.hypothesis
    assert cause.signature.endswith("|")


def test_unknown_span_gives_an_empty_path(make_span: SpanFactory) -> None:
    trace = build_traces([make_span("root", operation=Operation.AGENT)])[0]
    finding = Finding(
        trace_id="t1", rule="span_error", span_id="ghost", evidence="x"
    )

    assert probable_cause(trace, finding).path == ()


def test_parent_cycle_does_not_loop_forever(make_span: SpanFactory) -> None:
    trace = build_traces(
        [
            make_span("a", parent="b", status=SpanStatus.ERROR),
            make_span("b", parent="a", start_s=1),
        ]
    )[0]
    finding = Finding(
        trace_id="t1", rule="span_error", span_id="a", evidence="x"
    )

    assert set(probable_cause(trace, finding).path) <= {"a", "b"}


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("timeout after 31s", "Timeout after 45s"),
        (
            "order 9f2f958c1a2b not found",
            "order 0aa1bb22cc33 not found",
        ),
    ],
)
def test_similar_errors_share_a_normalized_form(
    first: str, second: str
) -> None:
    assert normalize_error(first) == normalize_error(second)


def test_different_errors_stay_different() -> None:
    assert normalize_error("timeout") != normalize_error("rate limited")


def test_normalized_error_is_truncated_and_has_no_separator() -> None:
    result = normalize_error("a|b " * 100)

    assert len(result) <= 80
    assert "|" not in result


def test_a_pipe_in_the_agent_name_does_not_break_the_signature(
    make_span: SpanFactory,
) -> None:
    trace = build_traces(
        [
            make_span("root", operation=Operation.AGENT, agent="billing|v2"),
            make_span(
                "tool",
                parent="root",
                operation=Operation.TOOL,
                status=SpanStatus.ERROR,
                agent="billing|v2",
            ),
        ]
    )[0]
    [finding] = SpanError().evaluate(trace, EMPTY)

    signature = probable_cause(trace, finding).signature

    assert len(signature.split("|")) == 4
    assert signature.split("|")[0] == "billing_v2"
