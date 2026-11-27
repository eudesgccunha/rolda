"""Tests for the per-span token rule."""

from collections.abc import Callable
from random import Random

from rolda.detection import Baseline, DetectionConfig, SpanTokenOutlier
from rolda.traces import Operation, Span, build_traces

SpanFactory = Callable[..., Span]


def _trace(make_span: SpanFactory, trace_id: str, tokens: int) -> list[Span]:
    return [
        make_span("root", trace_id=trace_id, operation=Operation.AGENT),
        make_span(
            "chat",
            trace_id=trace_id,
            parent="root",
            operation=Operation.LLM,
            start_s=1,
            input_tokens=tokens,
            output_tokens=50,
        ),
        make_span(
            "tool",
            trace_id=trace_id,
            parent="root",
            operation=Operation.TOOL,
            start_s=2,
            tool_name="search",
        ),
    ]


def _baseline(make_span: SpanFactory, count: int) -> Baseline:
    rng = Random(5)  # noqa: S311 - seeded test data, not crypto
    traces = []
    for i in range(count):
        tokens = int(rng.lognormvariate(6.2, 0.3))
        traces.extend(build_traces(_trace(make_span, f"h{i}", tokens)))
    return Baseline.from_traces(traces)


def test_one_huge_prompt_is_flagged(make_span: SpanFactory) -> None:
    baseline = _baseline(make_span, 60)
    big = build_traces(_trace(make_span, "x", 500 * 8))[0]

    [finding] = SpanTokenOutlier(DetectionConfig()).evaluate(big, baseline)

    assert finding.rule == "span_token_outlier"
    assert finding.span_id == "chat"
    assert "tokens" in finding.evidence


def test_normal_prompt_is_not_flagged(make_span: SpanFactory) -> None:
    baseline = _baseline(make_span, 60)
    normal = build_traces(_trace(make_span, "x", 500))[0]

    assert SpanTokenOutlier(DetectionConfig()).evaluate(normal, baseline) == ()


def test_needs_enough_samples(make_span: SpanFactory) -> None:
    baseline = _baseline(make_span, 10)
    big = build_traces(_trace(make_span, "x", 500 * 8))[0]

    assert SpanTokenOutlier(DetectionConfig()).evaluate(big, baseline) == ()


def test_spans_without_token_counts_are_ignored(
    make_span: SpanFactory,
) -> None:
    baseline = _baseline(make_span, 60)
    trace = build_traces(
        [
            make_span("root", operation=Operation.AGENT),
            make_span("chat", parent="root", operation=Operation.LLM),
        ]
    )[0]

    assert SpanTokenOutlier(DetectionConfig()).evaluate(trace, baseline) == ()


def test_rule_has_its_own_threshold(make_span: SpanFactory) -> None:
    baseline = _baseline(make_span, 60)
    mild = build_traces(_trace(make_span, "x", 750))[0]

    default = SpanTokenOutlier(DetectionConfig()).evaluate(mild, baseline)
    strict = SpanTokenOutlier(DetectionConfig(span_token_z=0.5)).evaluate(
        mild, baseline
    )

    assert default == ()
    assert [f.span_id for f in strict] == ["chat"]
