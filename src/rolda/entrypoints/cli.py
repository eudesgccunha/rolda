"""Command line: label incidents and export evals."""

import argparse
import asyncio
import os
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from rolda.incidents import (
    Label,
    LabelSource,
    LabelStore,
    UnknownIncidentError,
)
from rolda.judge import Verdict


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rolda")
    commands = parser.add_subparsers(dest="command", required=True)
    label = commands.add_parser("label", help="label an incident")
    label.add_argument("trace_id")
    label.add_argument("rule")
    label.add_argument("verdict", choices=[v.value for v in Verdict])
    label.add_argument("--reason", default="")
    label.add_argument("--labeler", default="cli")
    return parser


def _default_label_store() -> LabelStore:
    from rolda.adapters.postgres import PostgresLabelStore
    from rolda.entrypoints.settings import load_settings

    return PostgresLabelStore(load_settings(os.environ).postgres_dsn)


def main(
    argv: Sequence[str] | None = None,
    *,
    label_store: LabelStore | None = None,
    clock: Callable[[], datetime] = _utc_now,
) -> int:
    """Run one command. Return the process exit code."""
    args = _parser().parse_args(argv)
    store = label_store or _default_label_store()
    label = Label(
        trace_id=args.trace_id,
        rule=args.rule,
        source=LabelSource.HUMAN,
        verdict=Verdict(args.verdict),
        reason=args.reason,
        labeler=args.labeler,
        labeled_at=clock(),
    )
    try:
        asyncio.run(store.upsert(label))
    except UnknownIncidentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"labeled {label.trace_id} {label.rule}: {args.verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
