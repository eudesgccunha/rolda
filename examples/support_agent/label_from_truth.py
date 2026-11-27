"""Label incidents from the simulator's ground truth. Plumbing only.

Usage: label_from_truth.py TRUTH.jsonl  (needs POSTGRES_USER/PASSWORD)

Every incident on a session with an injected fault becomes `failure`. An
incident on a healthy session becomes `false_alarm`. The labeler is
`simulator-truth`. These are NOT human labels: a judge scored against them
measures the simulator, not real agreement. Use them to prove that the
judge call, schema and parser work end to end.
"""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from rolda.adapters.postgres import PostgresLabelStore
from rolda.incidents import Label, LabelSource
from rolda.judge import Verdict

LABELER = "simulator-truth"


def load_truth(path: Path) -> dict[str, str]:
    """Read the ground-truth file: trace id to injected fault."""
    return {
        row["trace_id"]: row["fault"]
        for row in map(json.loads, path.read_text().splitlines())
    }


async def main() -> None:
    truth = load_truth(Path(sys.argv[1]))
    dsn = (
        f"postgresql://{os.environ['POSTGRES_USER']}:"
        f"{os.environ['POSTGRES_PASSWORD']}@127.0.0.1:5432/rolda"
    )
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT trace_id, rule FROM incidents WHERE trace_id = ANY(%s)",
            (list(truth),),
        ).fetchall()
    store = PostgresLabelStore(dsn)
    counts = {Verdict.FAILURE: 0, Verdict.FALSE_ALARM: 0}
    for trace_id, rule in rows:
        verdict = (
            Verdict.FALSE_ALARM
            if truth[trace_id] == "healthy"
            else Verdict.FAILURE
        )
        await store.upsert(
            Label(
                trace_id=trace_id,
                rule=rule,
                source=LabelSource.HUMAN,
                verdict=verdict,
                reason=f"simulator fault: {truth[trace_id]}",
                labeler=LABELER,
                labeled_at=datetime.now(UTC),
            )
        )
        counts[verdict] += 1
    print(f"labeled {len(rows)} incidents: {dict(counts)}")


if __name__ == "__main__":
    asyncio.run(main())
