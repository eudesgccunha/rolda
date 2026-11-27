"""Apply the schema migrations: ``python -m rolda.entrypoints.migrate``."""

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from rolda.adapters.migrations import (
    ClickHouseMigrationTarget,
    PostgresMigrationTarget,
)
from rolda.entrypoints.settings import SettingsError, load_settings
from rolda.migrations import (
    MigrationChecksumError,
    MigrationFileError,
    MigrationTarget,
    apply_pending,
    load_migrations,
)

MIGRATIONS = Path(__file__).parent.parent / "migrations"


async def _run(only: str | None) -> int:
    settings = load_settings(os.environ)
    targets: list[tuple[str, MigrationTarget]] = [
        ("postgres", PostgresMigrationTarget(settings.postgres_dsn)),
        ("clickhouse", ClickHouseMigrationTarget(settings)),
    ]
    for name, target in targets:
        if only not in (None, name):
            continue
        done = await apply_pending(target, load_migrations(MIGRATIONS / name))
        print(f"{name}: applied {', '.join(done) if done else 'nothing'}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the migrations. Return the process exit code."""
    parser = argparse.ArgumentParser(prog="rolda-migrate")
    parser.add_argument("--only", choices=["postgres", "clickhouse"])
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        return asyncio.run(_run(args.only))
    except SettingsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (MigrationFileError, MigrationChecksumError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
