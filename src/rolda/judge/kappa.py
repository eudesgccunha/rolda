"""Cohen's kappa: agreement between two raters, corrected for chance."""

from collections import Counter
from collections.abc import Sequence


def cohen_kappa(first: Sequence[str], second: Sequence[str]) -> float:
    """Return Cohen's kappa for two equally long label sequences.

    1.0 is perfect agreement, 0.0 is what chance alone would give and
    negative values mean systematic disagreement.
    """
    if len(first) != len(second):
        msg = "sequences must have the same length"
        raise ValueError(msg)
    if not first:
        msg = "cannot score an empty sequence"
        raise ValueError(msg)
    total = len(first)
    observed = sum(a == b for a, b in zip(first, second, strict=True)) / total
    counts_a = Counter(first)
    counts_b = Counter(second)
    expected = sum(counts_a[label] * counts_b[label] for label in counts_a) / (
        total * total
    )
    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)
