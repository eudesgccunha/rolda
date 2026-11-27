"""Tests for the detection rules."""

import json
from collections.abc import Callable
from pathlib import Path

from rolda.detection import (
    Baseline,
    Confidence,
    DetectionConfig,
    LatencyOutlier,
    SpanError,
    TokenOutlier,
    ToolLoop,
    default_rules,
)
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


def _sdk_traces() -> dict[str, Trace]:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    traces = build_traces(normalize_span(row) for row in rows)
    return {trace.trace_id[:8]: trace for trace in traces}


def test_span_error_points_at_the_origin_not_the_root(
    make_span: SpanFactory,
) -> None:
    trace = build_traces(
        [
            make_span(
                "root", operation=Operation.AGENT, status=SpanStatus.ERROR
            ),
            make_span(
                "tool",
                parent="root",
                operation=Operation.TOOL,
                start_s=1,
                status=SpanStatus.ERROR,
            ),
        ]
    )[0]

    findings = SpanError().evaluate(trace, EMPTY)

    assert [f.span_id for f in findings] == ["tool"]
    assert findings[0].rule == "span_error"
    assert "boom" in findings[0].evidence


def test_span_error_on_real_sdk_trace() -> None:
    trace = _sdk_traces()["1aea792b"]

    findings = SpanError().evaluate(trace, EMPTY)

    assert len(findings) == 1
    span = next(s for s in trace.spans if s.span_id == findings[0].span_id)
    assert span.operation is Operation.TOOL


def test_span_error_ignores_healthy_trace() -> None:
    assert SpanError().evaluate(_sdk_traces()["54daf741"], EMPTY) == ()


def test_tool_loop_detected_on_real_sdk_trace() -> None:
    findings = ToolLoop(DetectionConfig()).evaluate(
        _sdk_traces()["9eea290c"], EMPTY
    )

    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH
    assert "search_orders" in findings[0].evidence


def test_tool_loop_needs_identical_arguments(
    make_span: SpanFactory,
) -> None:
    trace = build_traces(
        [
            make_span(
                "a",
                operation=Operation.TOOL,
                tool_name="s",
                tool_arguments=f'{{"q": {i}}}',
                start_s=i,
            )
            for i in range(3)
        ]
    )[0]

    assert ToolLoop(DetectionConfig()).evaluate(trace, EMPTY) == ()


def test_tool_loop_without_arguments_is_low_confidence(
    make_span: SpanFactory,
) -> None:
    trace = build_traces(
        [
            make_span(
                f"s{i}", operation=Operation.TOOL, tool_name="s", start_s=i
            )
            for i in range(3)
        ]
    )[0]

    findings = ToolLoop(DetectionConfig()).evaluate(trace, EMPTY)

    assert [f.confidence for f in findings] == [Confidence.LOW]


def _history(make_span: SpanFactory, count: int) -> Baseline:
    traces = [
        build_traces(
            [
                make_span(
                    f"r{i}",
                    trace_id=f"h{i}",
                    operation=Operation.AGENT,
                    duration_ns=1_000 + (i % 5) * 10,
                ),
                make_span(
                    f"l{i}",
                    trace_id=f"h{i}",
                    parent=f"r{i}",
                    operation=Operation.LLM,
                    input_tokens=100 + (i % 5),
                    output_tokens=50,
                ),
            ]
        )[0]
        for i in range(count)
    ]
    return Baseline.from_traces(traces)


def _slow_trace(make_span: SpanFactory) -> Trace:
    return build_traces(
        [
            make_span("r", operation=Operation.AGENT, duration_ns=1_000_000),
            make_span(
                "l",
                parent="r",
                operation=Operation.LLM,
                input_tokens=90_000,
                output_tokens=50,
            ),
        ]
    )[0]


def test_outlier_rules_flag_extreme_trace(make_span: SpanFactory) -> None:
    baseline = _history(make_span, 40)
    trace = _slow_trace(make_span)
    config = DetectionConfig()

    latency = LatencyOutlier(config).evaluate(trace, baseline)
    tokens = TokenOutlier(config).evaluate(trace, baseline)

    assert [f.rule for f in latency] == ["latency_outlier"]
    assert [f.rule for f in tokens] == ["token_outlier"]


def test_outlier_rules_need_enough_samples(make_span: SpanFactory) -> None:
    baseline = _history(make_span, 29)
    trace = _slow_trace(make_span)
    config = DetectionConfig()

    assert LatencyOutlier(config).evaluate(trace, baseline) == ()
    assert TokenOutlier(config).evaluate(trace, baseline) == ()


def test_outlier_rules_still_flag_an_extreme_value_when_mad_is_zero(
    make_span: SpanFactory,
) -> None:
    flat = Baseline.from_traces(
        [
            build_traces(
                [
                    make_span(
                        f"r{i}",
                        trace_id=f"h{i}",
                        operation=Operation.AGENT,
                        duration_ns=1_000,
                    )
                ]
            )[0]
            for i in range(40)
        ]
    )

    result = LatencyOutlier(DetectionConfig()).evaluate(
        _slow_trace(make_span), flat
    )

    assert [f.rule for f in result] == ["latency_outlier"]


def test_default_rules_lists_the_rules() -> None:
    names = [rule.name for rule in default_rules(DetectionConfig())]

    assert names == [
        "span_error",
        "tool_loop",
        "latency_outlier",
        "span_latency_outlier",
        "token_outlier",
        "span_token_outlier",
    ]
