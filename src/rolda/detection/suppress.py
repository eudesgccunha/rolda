"""Drop outlier findings that a stronger finding already explains."""

from collections.abc import Sequence

from rolda.detection.model import Finding

PRIMARY_RULES = frozenset({"span_error", "tool_loop"})
OUTLIER_RULES = frozenset(
    {
        "latency_outlier",
        "token_outlier",
        "span_latency_outlier",
        "span_token_outlier",
    }
)


def suppress_redundant(findings: Sequence[Finding]) -> list[Finding]:
    """Remove outlier findings from a trace that has an error or a loop.

    A looping or failing session is naturally longer or heavier. Reporting
    the outlier as well would raise several incidents for one cause.
    """
    explained = any(f.rule in PRIMARY_RULES for f in findings)
    return [f for f in findings if not (explained and f.rule in OUTLIER_RULES)]
