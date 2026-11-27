"""Tests for the migration runner (no database needed)."""

import asyncio
import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from rolda.migrations import (
    Migration,
    MigrationChecksumError,
    MigrationFileError,
    apply_pending,
    load_migrations,
    split_statements,
)

SHIPPED = Path(__file__).parent.parent.parent / "src" / "rolda" / "migrations"


class _MemoryTarget:
    """Records what the runner does."""

    def __init__(self, applied: Mapping[str, str] | None = None) -> None:
        self._applied = dict(applied or {})
        self.executed: list[str] = []
        self.locked_calls = 0

    @asynccontextmanager
    async def locked(self) -> AsyncIterator[None]:
        self.locked_calls += 1
        yield

    async def applied(self) -> dict[str, str]:
        return dict(self._applied)

    async def apply(self, migration: Migration) -> None:
        self.executed.append(migration.version)
        self._applied[migration.version] = migration.checksum


def _write(directory: Path, name: str, sql: str = "SELECT 1;") -> None:
    (directory / name).write_text(sql, encoding="utf-8")


def test_migrations_load_in_numeric_order(tmp_path: Path) -> None:
    _write(tmp_path, "010_later.sql")
    _write(tmp_path, "002_second.sql")
    _write(tmp_path, "001_first.sql")

    loaded = load_migrations(tmp_path)

    assert [m.version for m in loaded] == ["001", "002", "010"]
    assert loaded[0].name == "first"


@pytest.mark.parametrize(
    "name", ["init.sql", "1_short.sql", "001-dash.sql", "001_UPPER.sql"]
)
def test_badly_named_files_are_rejected(tmp_path: Path, name: str) -> None:
    _write(tmp_path, name)

    with pytest.raises(MigrationFileError, match="name"):
        load_migrations(tmp_path)


def test_duplicate_versions_are_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "001_a.sql")
    _write(tmp_path, "001_b.sql")

    with pytest.raises(MigrationFileError, match="duplicate"):
        load_migrations(tmp_path)


def test_checksum_ignores_line_endings(tmp_path: Path) -> None:
    _write(tmp_path, "001_a.sql", "SELECT 1;\nSELECT 2;\n")
    first = load_migrations(tmp_path)[0].checksum
    _write(tmp_path, "001_a.sql", "SELECT 1;\r\nSELECT 2;\r\n")

    assert load_migrations(tmp_path)[0].checksum == first


def test_only_pending_migrations_run_in_order(tmp_path: Path) -> None:
    for name in ("001_a.sql", "002_b.sql", "003_c.sql"):
        _write(tmp_path, name)
    migrations = load_migrations(tmp_path)
    target = _MemoryTarget({"001": migrations[0].checksum})

    done = asyncio.run(apply_pending(target, migrations))

    assert done == ["002", "003"]
    assert target.executed == ["002", "003"]
    assert target.locked_calls == 1


def test_running_twice_applies_nothing_the_second_time(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "001_a.sql")
    migrations = load_migrations(tmp_path)
    target = _MemoryTarget()

    first = asyncio.run(apply_pending(target, migrations))
    second = asyncio.run(apply_pending(target, migrations))

    assert (first, second) == (["001"], [])


def test_a_changed_applied_migration_is_refused(tmp_path: Path) -> None:
    _write(tmp_path, "001_a.sql", "SELECT 1;")
    migrations = load_migrations(tmp_path)
    target = _MemoryTarget({"001": "0" * 64})

    with pytest.raises(MigrationChecksumError, match="001"):
        asyncio.run(apply_pending(target, migrations))
    assert target.executed == []


def test_versions_unknown_to_this_code_are_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "001_a.sql")
    migrations = load_migrations(tmp_path)
    target = _MemoryTarget({"099": "x" * 64})

    assert asyncio.run(apply_pending(target, migrations)) == ["001"]


def test_statements_are_split_and_comments_dropped() -> None:
    sql = """
-- header; with a semicolon
CREATE DATABASE IF NOT EXISTS rolda;

CREATE TABLE IF NOT EXISTS rolda.t (a Int8) -- trailing; comment
ENGINE = MergeTree ORDER BY a;
"""

    assert split_statements(sql) == [
        "CREATE DATABASE IF NOT EXISTS rolda",
        "CREATE TABLE IF NOT EXISTS rolda.t (a Int8)\n"
        "ENGINE = MergeTree ORDER BY a",
    ]


@pytest.mark.parametrize("engine", ["postgres", "clickhouse"])
def test_shipped_migrations_load(engine: str) -> None:
    loaded = load_migrations(SHIPPED / engine)

    assert loaded
    assert [m.version for m in loaded] == sorted(m.version for m in loaded)


@pytest.mark.parametrize("engine", ["postgres", "clickhouse"])
def test_shipped_migrations_are_safe_to_run_twice(engine: str) -> None:
    # The runner records what it applied, but Compose also runs these files
    # once on a new volume, so every statement must be idempotent.
    for migration in load_migrations(SHIPPED / engine):
        for statement in split_statements(migration.sql):
            if re.match(r"CREATE\s+(DATABASE|TABLE|INDEX)", statement, re.I):
                assert re.search(r"IF NOT EXISTS", statement, re.I), (
                    migration.version,
                    statement[:60],
                )
            if re.search(r"ADD\s+COLUMN", statement, re.I):
                assert re.search(
                    r"ADD\s+COLUMN\s+IF NOT EXISTS", statement, re.I
                )
            assert not re.match(r"\s*DROP\b", statement, re.I)
