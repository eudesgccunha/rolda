"""Runtime settings, read from the environment only."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import quote


class SettingsError(ValueError):
    """Raised when the environment is incomplete or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the worker process needs."""

    clickhouse_host: str
    clickhouse_port: int
    clickhouse_user: str
    clickhouse_password: str
    postgres_dsn: str
    window: timedelta
    interval: timedelta


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        msg = f"missing environment variable {name}"
        raise SettingsError(msg)
    return value


def _number(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        msg = f"{name} must be an integer, got {raw!r}"
        raise SettingsError(msg) from exc


def load_settings(env: Mapping[str, str]) -> Settings:
    """Build settings from environment variables."""
    pg_user = quote(_required(env, "POSTGRES_USER"), safe="")
    pg_password = quote(_required(env, "POSTGRES_PASSWORD"), safe="")
    pg_host = env.get("ROLDA_POSTGRES_HOST", "127.0.0.1")
    pg_port = _number(env, "ROLDA_POSTGRES_PORT", 5432)
    return Settings(
        clickhouse_host=env.get("ROLDA_CLICKHOUSE_HOST", "127.0.0.1"),
        clickhouse_port=_number(env, "ROLDA_CLICKHOUSE_PORT", 8123),
        clickhouse_user=_required(env, "CLICKHOUSE_USER"),
        clickhouse_password=_required(env, "CLICKHOUSE_PASSWORD"),
        postgres_dsn=(
            f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/rolda"
        ),
        window=timedelta(seconds=_number(env, "ROLDA_WINDOW_SECONDS", 300)),
        interval=timedelta(seconds=_number(env, "ROLDA_INTERVAL_SECONDS", 60)),
    )
