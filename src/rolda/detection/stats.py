"""Robust statistics for outlier rules."""

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

# Iglewicz and Hoaglin modified z-score constant.
_MODIFIED_Z = 0.6745


# Modified z-score: 0.6745 * (x - median) / MAD. 0.6745 is the Iglewicz and
# Hoaglin constant. The scale used below is MAD / 0.6745, a standard deviation
# estimate, so both branches give a comparable score.
_MEAN_AD_TO_SIGMA = 1.253314
# A history with no spread at all says nothing about normal variation. Assume
# a spread of 5% of the typical value, so a change of a few percent is normal
# and a large one is not.
_MIN_RELATIVE_SPREAD = 0.05


@dataclass(frozen=True, slots=True)
class Stats:
    """What the outlier score needs from a group of samples.

    Keeping only these four numbers lets the baseline forget the samples.
    """

    count: int
    median: float
    mad: float
    mean_ad: float

    @classmethod
    def from_samples(cls, samples: Sequence[float]) -> "Stats":
        """Summarize samples. An empty group has a count of zero."""
        if not samples:
            return cls(0, 0.0, 0.0, 0.0)
        centre = median(samples)
        deviations = [abs(sample - centre) for sample in samples]
        return cls(
            count=len(samples),
            median=centre,
            mad=median(deviations),
            mean_ad=sum(deviations) / len(deviations),
        )


def robust_z_stats(value: float, stats: Stats) -> float | None:
    """Return the modified z-score of ``value`` against a group.

    Uses the median and the MAD. When the MAD is zero (more than half of the
    samples are equal) it uses the mean absolute deviation instead, with a
    floor of 5% of the median, so a constant history can still flag an
    extreme value. It is None only when there is no scale at all, as for a
    history of zeros or an empty group.
    """
    if stats.count == 0:
        return None
    if stats.mad > 0:
        return _MODIFIED_Z * (value - stats.median) / stats.mad
    scale = max(
        _MEAN_AD_TO_SIGMA * stats.mean_ad,
        _MIN_RELATIVE_SPREAD * abs(stats.median),
    )
    if scale == 0:
        return None
    return (value - stats.median) / scale


def robust_z(value: float, samples: Sequence[float]) -> float | None:
    """Return the modified z-score of ``value`` against raw samples."""
    return robust_z_stats(value, Stats.from_samples(samples))
