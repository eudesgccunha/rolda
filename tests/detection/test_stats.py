"""Tests for the robust z-score."""

import pytest

from rolda.detection.stats import Stats, robust_z, robust_z_stats


def test_value_at_the_median_scores_zero() -> None:
    assert robust_z(10.0, [8.0, 9.0, 10.0, 11.0, 12.0]) == 0.0


def test_far_value_scores_above_threshold() -> None:
    samples = [10.0, 11.0, 9.0, 10.5, 9.5, 10.2, 9.8]

    score = robust_z(100.0, samples)

    assert score is not None
    assert score > 3.5


def test_a_constant_history_still_scores_an_extreme_value() -> None:
    score = robust_z(90_000.0, [1_200.0] * 40)

    assert score is not None
    assert score > 100


def test_a_constant_history_does_not_flag_a_tiny_change() -> None:
    score = robust_z(1_230.0, [1_200.0] * 40)

    assert score is not None
    assert score < 1


def test_zero_mad_with_some_spread_uses_the_mean_deviation() -> None:
    # Most values are equal, so MAD is 0, but one value differs.
    samples = [10.0] * 9 + [20.0]

    score = robust_z(40.0, samples)

    assert score is not None
    assert score > 3.5


def test_a_history_of_zeros_has_no_scale() -> None:
    assert robust_z(5.0, [0.0] * 40) is None


def test_empty_samples_return_none() -> None:
    assert robust_z(5.0, []) is None


def test_matches_modified_z_score_formula() -> None:
    # median 3, MAD 1, so 0.6745 * (6 - 3) / 1
    score = robust_z(6.0, [1.0, 2.0, 3.0, 4.0, 5.0])

    assert score == pytest.approx(0.6745 * 3)


def _reference(value: float, samples: list[float]) -> float | None:
    """The score computed straight from the samples (the old definition)."""
    from statistics import median

    centre = median(samples)
    deviations = [abs(s - centre) for s in samples]
    mad = median(deviations)
    if mad > 0:
        return 0.6745 * (value - centre) / mad
    scale = max(
        1.253314 * sum(deviations) / len(deviations), 0.05 * abs(centre)
    )
    return None if scale == 0 else (value - centre) / scale


def test_stats_give_the_same_score_as_the_samples() -> None:
    import random

    rng = random.Random(11)  # noqa: S311 - seeded test data, not crypto
    for size in (1, 2, 3, 10, 31, 200):
        for _ in range(20):
            kind = rng.choice(["spread", "constant", "mostly-equal"])
            if kind == "spread":
                samples = [rng.lognormvariate(5, 0.7) for _ in range(size)]
            elif kind == "constant":
                samples = [rng.choice([0.0, 7.0, 1200.0])] * size
            else:
                samples = [10.0] * size
                samples[: size // 3] = [
                    rng.random() * 50 for _ in range(size // 3)
                ]
            value = rng.uniform(0, 5000)

            expected = _reference(value, samples)
            actual = robust_z_stats(value, Stats.from_samples(samples))

            if expected is None:
                assert actual is None
            else:
                assert actual == pytest.approx(expected)


def test_stats_hold_a_count_and_no_samples() -> None:
    stats = Stats.from_samples([1.0, 2.0, 3.0, 4.0])

    assert stats.count == 4
    assert stats.median == 2.5
    assert stats.mad == 1.0


def test_stats_of_nothing_is_empty() -> None:
    assert Stats.from_samples([]).count == 0
