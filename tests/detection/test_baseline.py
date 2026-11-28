"""Tests for the baseline built from compact, mergeable samples."""

from array import array
from collections.abc import Callable
from random import Random

import pytest

from rolda.detection.baseline import Baseline, BaselineSamples
from rolda.traces import Operation, Span, Trace, build_traces

SpanFactory = Callable[..., Span]


def _traces(make_span: SpanFactory, count: int, seed: int) -> list[Trace]:
    rng = Random(seed)  # noqa: S311 - seeded test data, not crypto
    spans: list[Span] = []
    for i in range(count):
        trace_id = f"t{seed}-{i}"
        spans.append(
            make_span(
                "root",
                trace_id=trace_id,
                operation=Operation.AGENT,
                duration_ns=rng.randint(10_000_000, 90_000_000),
            )
        )
        spans.append(
            make_span(
                "chat",
                trace_id=trace_id,
                parent="root",
                operation=Operation.LLM,
                start_s=1,
                duration_ns=rng.randint(1_000_000, 9_000_000),
                input_tokens=rng.randint(300, 900),
                output_tokens=rng.randint(10, 100),
            )
        )
        spans.append(
            make_span(
                "tool",
                trace_id=trace_id,
                parent="root",
                operation=Operation.TOOL,
                start_s=2,
                duration_ns=rng.randint(1_000_000, 5_000_000),
                tool_name="search",
            )
        )
    return build_traces(spans)


def test_samples_are_kept_in_compact_float_arrays(
    make_span: SpanFactory,
) -> None:
    samples = BaselineSamples()

    samples.add_traces(_traces(make_span, 5, 1))

    assert isinstance(samples.durations["agent-a"], array)
    assert samples.durations["agent-a"].itemsize == 8
    assert len(samples.durations["agent-a"]) == 5
    assert samples.trace_count == 5


def test_merged_slices_give_the_same_baseline_as_the_whole_history(
    make_span: SpanFactory,
) -> None:
    first, second, third = (_traces(make_span, 40, seed) for seed in (1, 2, 3))
    slices = []
    for part in (first, second, third):
        samples = BaselineSamples()
        samples.add_traces(part)
        slices.append(samples)

    merged = Baseline.from_samples(slices)
    whole = Baseline.from_traces(first + second + third)

    assert merged == whole


def test_a_baseline_keeps_statistics_not_samples(
    make_span: SpanFactory,
) -> None:
    baseline = Baseline.from_traces(_traces(make_span, 50, 1))

    stats = baseline.durations["agent-a"]

    assert stats.count == 50
    assert stats.median > 0
    assert not hasattr(stats, "__iter__")


def test_span_groups_are_kept_on_the_log_scale(make_span: SpanFactory) -> None:
    baseline = Baseline.from_traces(_traces(make_span, 50, 1))

    [(key, stats)] = [
        (k, v) for k, v in baseline.span_durations.items() if "tool" in k
    ]

    assert key.startswith("agent-a|tool|")
    # ln of 1e6..5e6 ns is between 13.8 and 15.5.
    assert 13.0 < stats.median < 16.0


def test_an_empty_baseline_has_no_groups() -> None:
    baseline = Baseline.from_samples([])

    assert baseline.durations == {}
    assert baseline == Baseline.from_traces([])


def test_samples_can_be_merged_in_any_order(make_span: SpanFactory) -> None:
    parts = []
    for seed in (4, 5):
        samples = BaselineSamples()
        samples.add_traces(_traces(make_span, 30, seed))
        parts.append(samples)

    forward = Baseline.from_samples(parts)
    backward = Baseline.from_samples(parts[::-1])

    assert forward.durations["agent-a"].median == pytest.approx(
        backward.durations["agent-a"].median
    )


def test_a_trace_without_its_root_is_not_part_of_the_baseline(
    make_span: SpanFactory,
) -> None:
    orphan = build_traces(
        [
            make_span(
                "tool",
                trace_id="cut",
                parent="root-in-another-slice",
                operation=Operation.TOOL,
                duration_ns=5,
            )
        ]
    )
    samples = BaselineSamples()

    samples.add_traces(orphan)

    assert samples.trace_count == 0
    assert samples.durations == {}
