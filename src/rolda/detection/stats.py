"""Robust statistics for outlier rules."""

from collections.abc import Sequence
from statistics import median

# Iglewicz and Hoaglin modified z-score constant.
_MODIFIED_Z = 0.6745


def robust_z(value: float, samples: Sequence[float]) -> float | None:
    """Return the modified z-score of ``value``, or None if undefined.

    Uses the median and the MAD. A MAD of zero gives no usable scale, so
    the score is undefined.
    """
    if not samples:
        return None
    centre = median(samples)
    mad = median(abs(sample - centre) for sample in samples)
    if mad == 0:
        return None
    return _MODIFIED_Z * (value - centre) / mad
