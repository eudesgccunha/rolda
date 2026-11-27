"""Robust statistics for outlier rules."""

from collections.abc import Sequence
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


def robust_z(value: float, samples: Sequence[float]) -> float | None:
    """Return the modified z-score of ``value``, or None if undefined.

    Uses the median and the MAD. When the MAD is zero (more than half of the
    samples are equal) it uses the mean absolute deviation instead, with a
    floor of 5% of the median, so a constant history can still flag an
    extreme value. It is None only when there is no scale at all, as for a
    history of zeros.
    """
    if not samples:
        return None
    centre = median(samples)
    deviations = [abs(sample - centre) for sample in samples]
    mad = median(deviations)
    if mad > 0:
        return _MODIFIED_Z * (value - centre) / mad
    scale = max(
        _MEAN_AD_TO_SIGMA * sum(deviations) / len(deviations),
        _MIN_RELATIVE_SPREAD * abs(centre),
    )
    if scale == 0:
        return None
    return (value - centre) / scale
