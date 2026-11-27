"""Tests for the per-span latency rule."""

from collections.abc import Callable
from random import Random

from rolda.detection import Baseline, DetectionConfig, SpanLatencyOutlier
from rolda.traces import Operation, Span, build_traces

SpanFactory = Callable[..., Span]


def _trace(
    make_span: SpanFactory, trace_id: str, chat_ns: int, tool_ns: int
) -> list[Span]:
    return [
        make_span(
            "root",
            trace_id=trace_id,
            operation=Operation.AGENT,
            duration_ns=chat_ns + tool_ns + 1_000_000,
        ),
        make_span(
            "chat",
            trace_id=trace_id,
            parent="root",
            operation=Operation.LLM,
            start_s=1,
            duration_ns=chat_ns,
        ),
        make_span(
            "tool",
            trace_id=trace_id,
            parent="root",
            operation=Operation.TOOL,
            start_s=2,
            duration_ns=tool_ns,
            tool_name="search",
        ),
    ]


def _baseline(make_span: SpanFactory, count: int) -> Baseline:
    rng = Random(3)  # noqa: S311 - seeded test data, not crypto
    traces = []
    for i in range(count):
        chat = int(rng.lognormvariate(16.0, 0.4))
        tool = int(rng.lognormvariate(15.0, 0.4))
        traces.extend(build_traces(_trace(make_span, f"h{i}", chat, tool)))
    return Baseline.from_traces(traces)


def test_one_slow_model_call_is_flagged_even_if_the_trace_total_is_normal(
    make_span: SpanFactory,
) -> None:
    baseline = _baseline(make_span, 60)
    slow = build_traces(_trace(make_span, "x", 8_900_000 * 5, 3_269_000))[0]

    [finding] = SpanLatencyOutlier(DetectionConfig()).evaluate(slow, baseline)

    assert finding.rule == "span_latency_outlier"
    assert finding.span_id == "chat"
    assert "chat" in finding.evidence


def test_normal_trace_is_not_flagged(make_span: SpanFactory) -> None:
    baseline = _baseline(make_span, 60)
    normal = build_traces(_trace(make_span, "x", 8_900_000, 3_269_000))[0]

    assert (
        SpanLatencyOutlier(DetectionConfig()).evaluate(normal, baseline) == ()
    )


def test_needs_enough_samples(make_span: SpanFactory) -> None:
    baseline = _baseline(make_span, 10)
    slow = build_traces(_trace(make_span, "x", 8_900_000 * 5, 3_269_000))[0]

    assert SpanLatencyOutlier(DetectionConfig()).evaluate(slow, baseline) == ()


def test_only_the_worst_span_is_reported(make_span: SpanFactory) -> None:
    baseline = _baseline(make_span, 60)
    both = build_traces(_trace(make_span, "x", 8_900_000 * 6, 3_269_000 * 4))[
        0
    ]

    findings = SpanLatencyOutlier(DetectionConfig()).evaluate(both, baseline)

    assert len(findings) == 1


def test_rule_has_its_own_threshold(make_span: SpanFactory) -> None:
    baseline = _baseline(make_span, 60)
    mild = build_traces(
        _trace(make_span, "x", int(8_900_000 * 1.5), 3_269_000)
    )[0]

    default = SpanLatencyOutlier(DetectionConfig()).evaluate(mild, baseline)
    strict = SpanLatencyOutlier(DetectionConfig(span_latency_z=0.5)).evaluate(
        mild, baseline
    )

    assert default == ()
    assert [f.span_id for f in strict] == ["chat"]


def test_threshold_falls_back_to_the_shared_value() -> None:
    config = DetectionConfig(z_threshold=4.0, token_z=2.5, span_latency_z=None)

    assert config.z_for("token_outlier") == 2.5
    assert config.z_for("span_token_outlier") == 4.0
    assert config.z_for("latency_outlier") == 4.0
    assert config.z_for("span_latency_outlier") == 4.0


def test_defaults_use_the_calibrated_thresholds() -> None:
    config = DetectionConfig()

    assert config.z_for("span_latency_outlier") == 3.0
    assert config.z_for("token_outlier") == 3.5
    assert config.z_for("span_token_outlier") == 3.5
    assert config.z_for("latency_outlier") == 3.5
