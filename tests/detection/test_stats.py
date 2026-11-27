"""Tests for the robust z-score."""

import pytest

from rolda.detection.stats import robust_z


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
