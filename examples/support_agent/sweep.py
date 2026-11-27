"""Sweep the outlier threshold against the ground truth of a run.

Usage: sweep.py TRUTH.jsonl START_ISO
Reads spans from ClickHouse (CLICKHOUSE_* env vars). Writes nothing and
sends no alerts: it only replays the rules and prints a table.
START_ISO is when the run started, for example 2026-11-26T21:07:00Z.
"""

import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rolda.adapters.clickhouse import ClickHouseSpanSource
from rolda.detection import (
    Baseline,
    DetectionConfig,
    default_rules,
    suppress_redundant,
)
from rolda.entrypoints.settings import load_settings
from rolda.traces import build_traces

OUTLIERS = ("latency_outlier", "span_latency_outlier", "token_outlier")
FAULT_RULES = {
    "latency_outlier": {"latency_outlier", "span_latency_outlier"},
    "token_blowup": {"token_outlier"},
}
LAG = timedelta(minutes=2)
THRESHOLDS = (2.5, 3.0, 3.25, 3.5, 3.75, 4.0)


def load_truth(path: Path) -> dict[str, str]:
    """Read the ground-truth file: trace id to injected fault."""
    return {
        row["trace_id"]: row["fault"]
        for row in map(json.loads, path.read_text().splitlines())
    }


async def main() -> None:
    truth = load_truth(Path(sys.argv[1]))
    start = datetime.fromisoformat(sys.argv[2].replace("Z", "+00:00"))
    source = ClickHouseSpanSource(load_settings(os.environ))
    now = datetime.now(UTC)
    window = await source.spans_between(start - LAG, now)
    history = await source.spans_between(
        start - timedelta(days=7), start - LAG
    )
    baseline = Baseline.from_traces(build_traces(history))
    traces = [t for t in build_traces(window) if t.trace_id in truth]
    print(f"traces={len(traces)} baseline_traces={len(build_traces(history))}")
    print("z      latency  tokens  healthy_flagged  by_rule")
    for z in THRESHOLDS:
        rules = default_rules(DetectionConfig(z_threshold=z))
        found: dict[str, set[str]] = defaultdict(set)
        for trace in traces:
            findings = suppress_redundant(
                [f for r in rules for f in r.evaluate(trace, baseline)]
            )
            found[trace.trace_id] = {f.rule for f in findings}
        row = []
        for fault in ("latency_outlier", "token_blowup"):
            ids = [t for t, f in truth.items() if f == fault]
            hits = sum(bool(found[t] & FAULT_RULES[fault]) for t in ids)
            row.append(f"{hits}/{len(ids)}")
        healthy = [t for t, f in truth.items() if f == "healthy"]
        flagged = [t for t in healthy if found[t] & set(OUTLIERS)]
        by_rule = {
            rule: sum(rule in found[t] for t in healthy) for rule in OUTLIERS
        }
        print(
            f"{z:<5}  {row[0]:>7}  {row[1]:>6}  "
            f"{len(flagged):>3}/{len(healthy):<12} {by_rule}"
        )


if __name__ == "__main__":
    asyncio.run(main())
