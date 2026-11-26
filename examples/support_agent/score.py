"""Score Rolda's incidents against the ground truth of a run.

Usage: score.py TRUTH.jsonl  (needs POSTGRES_USER and POSTGRES_PASSWORD)
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import psycopg

# Which incident rules count as a correct detection of each injected fault.
EXPECTED = {
    "tool_timeout": {"span_error"},
    "rate_limit": {"span_error"},
    "tool_loop": {"tool_loop"},
    "latency_outlier": {"latency_outlier", "span_latency_outlier"},
    "token_blowup": {"token_outlier"},
}


def main() -> None:
    truth = {
        row["trace_id"]: row["fault"]
        for row in map(json.loads, Path(sys.argv[1]).read_text().splitlines())
    }
    dsn = (
        f"postgresql://{os.environ['POSTGRES_USER']}:"
        f"{os.environ['POSTGRES_PASSWORD']}@127.0.0.1:5432/rolda"
    )
    found: dict[str, set[str]] = defaultdict(set)
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT trace_id, rule FROM incidents WHERE trace_id = ANY(%s)",
            (list(truth),),
        ).fetchall()
    for trace_id, rule in rows:
        found[trace_id].add(rule)

    print("fault            n  detected  by_rule")
    for fault, rules in EXPECTED.items():
        ids = [t for t, f in truth.items() if f == fault]
        hits = [t for t in ids if found[t] & rules]
        by_rule = sorted({r for t in ids for r in found[t]})
        print(f"{fault:15} {len(ids):3}  {len(hits):3}       {by_rule}")
    healthy = [t for t, f in truth.items() if f == "healthy"]
    flagged = [t for t in healthy if found[t]]
    print(f"healthy        {len(healthy):3}  flagged={len(flagged)}")
    for rule in ("latency_outlier", "span_latency_outlier", "token_outlier"):
        total = sum(rule in r for r in found.values())
        right = sum(
            rule in found[t]
            for t, f in truth.items()
            if rule in {r for k, v in EXPECTED.items() if k == f for r in v}
        )
        print(f"{rule:21} flagged={total} on_matching_fault={right}")


if __name__ == "__main__":
    main()
