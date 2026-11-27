"""Versioned schema migrations, applied by a small runner.

The SQL files live next to this module, one directory per database:
``postgres/NNN_name.sql`` and ``clickhouse/NNN_name.sql``. A file is applied
once and recorded with its checksum. Every statement must be safe to run
twice, because Compose also runs the same files on a brand new volume.
"""

import hashlib
import logging
import re
from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

_NAME = re.compile(r"^(?P<version>\d{3})_(?P<name>[a-z0-9_]+)\.sql$")


class MigrationFileError(ValueError):
    """Raised when the migration files are not valid."""


class MigrationChecksumError(RuntimeError):
    """Raised when an applied migration was edited afterwards."""


@dataclass(frozen=True, slots=True)
class Migration:
    """One SQL file."""

    version: str
    name: str
    sql: str
    checksum: str


class MigrationTarget(Protocol):
    """Port to a database that holds its own migration records."""

    def locked(self) -> AbstractAsyncContextManager[None]:
        """Hold a lock so two runners never apply migrations together."""
        ...

    async def applied(self) -> dict[str, str]:
        """Return version to checksum of what is already applied."""
        ...

    async def apply(self, migration: Migration) -> None:
        """Run the migration and record it."""
        ...


def _checksum(sql: str) -> str:
    normalized = sql.replace("\r\n", "\n").encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def load_migrations(directory: Path) -> list[Migration]:
    """Read ``NNN_name.sql`` files from a directory, in version order."""
    found: dict[str, Migration] = {}
    for path in sorted(directory.glob("*.sql")):
        match = _NAME.match(path.name)
        if match is None:
            msg = f"bad migration file name: {path.name} (use NNN_name.sql)"
            raise MigrationFileError(msg)
        version = match["version"]
        if version in found:
            msg = f"duplicate migration version {version}"
            raise MigrationFileError(msg)
        sql = path.read_text(encoding="utf-8")
        found[version] = Migration(version, match["name"], sql, _checksum(sql))
    return [found[version] for version in sorted(found)]


def split_statements(sql: str) -> list[str]:
    """Split a script into statements, dropping ``--`` comments."""
    lines = [line.split("--", 1)[0].rstrip() for line in sql.splitlines()]
    text = "\n".join(lines)
    return [part.strip() for part in text.split(";") if part.strip()]


async def apply_pending(
    target: MigrationTarget, migrations: Sequence[Migration]
) -> list[str]:
    """Apply the migrations the database does not have. Return their versions.

    Raises ``MigrationChecksumError`` if an applied migration was changed.
    Versions the database has but this code does not are only logged, so a
    rollback of the image does not block.
    """
    done: list[str] = []
    async with target.locked():
        applied: Mapping[str, str] = await target.applied()
        known = {m.version for m in migrations}
        for version in sorted(set(applied) - known):
            logger.warning("database has unknown migration %s", version)
        for migration in migrations:
            recorded = applied.get(migration.version)
            if recorded is None:
                await target.apply(migration)
                done.append(migration.version)
            elif recorded != migration.checksum:
                msg = (
                    f"migration {migration.version} was changed after it "
                    "was applied; add a new migration instead"
                )
                raise MigrationChecksumError(msg)
    return done


__all__ = [
    "Migration",
    "MigrationChecksumError",
    "MigrationFileError",
    "MigrationTarget",
    "apply_pending",
    "load_migrations",
    "split_statements",
]
