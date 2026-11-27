"""Runtime settings, read from the environment only."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import quote, urlsplit

from rolda.detection import DetectionConfig


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
    max_catchup: timedelta = timedelta(hours=24)
    chunk: timedelta = timedelta(hours=1)
    status_host: str = "127.0.0.1"
    status_port: int = 9100
    webhook_url: str | None = None
    slack_webhook_url: str | None = None
    google_chat_webhook_url: str | None = None
    teams_webhook_url: str | None = None
    detection: DetectionConfig = field(default_factory=DetectionConfig)


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


def _port(env: Mapping[str, str], name: str, default: int) -> int:
    value = _number(env, name, default)
    if not 1 <= value <= 65535:
        msg = f"{name} must be between 1 and 65535, got {value}"
        raise SettingsError(msg)
    return value


def _z_score(
    env: Mapping[str, str], name: str, default: float | None
) -> float | None:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        msg = f"{name} must be a number, got {raw!r}"
        raise SettingsError(msg) from exc
    if not math.isfinite(value) or value <= 0:
        msg = f"{name} must be a finite number above 0, got {raw!r}"
        raise SettingsError(msg)
    return value


def _minimum_int(
    env: Mapping[str, str], name: str, minimum: int, default: int
) -> int:
    raw = env.get(name)
    if raw is None:
        return default
    value = _number(env, name, minimum)
    if value < minimum:
        msg = f"{name} must be at least {minimum}, got {raw!r}"
        raise SettingsError(msg)
    return value


def _detection(env: Mapping[str, str]) -> DetectionConfig:
    """Override the calibrated defaults with the values that are set."""
    base = DetectionConfig()
    shared = _z_score(env, "ROLDA_Z_THRESHOLD", base.z_threshold)
    return DetectionConfig(
        tool_loop_repeats=_minimum_int(
            env, "ROLDA_TOOL_LOOP_REPEATS", 2, base.tool_loop_repeats
        ),
        z_threshold=base.z_threshold if shared is None else shared,
        min_samples=_minimum_int(
            env, "ROLDA_MIN_SAMPLES", 1, base.min_samples
        ),
        latency_z=_z_score(env, "ROLDA_Z_LATENCY", base.latency_z),
        span_latency_z=_z_score(
            env, "ROLDA_Z_SPAN_LATENCY", base.span_latency_z
        ),
        token_z=_z_score(env, "ROLDA_Z_TOKENS", base.token_z),
        span_token_z=_z_score(env, "ROLDA_Z_SPAN_TOKENS", base.span_token_z),
    )


def _optional_url(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        msg = f"{name} must be an http or https URL with a host"
        raise SettingsError(msg)
    try:
        parts.port  # noqa: B018 - reading it validates the port
    except ValueError as exc:
        msg = f"{name} has an invalid port"
        raise SettingsError(msg) from exc
    return value


def load_postgres_dsn(env: Mapping[str, str]) -> str:
    """Build only the PostgreSQL DSN, for commands that need no ClickHouse."""
    user = quote(_required(env, "POSTGRES_USER"), safe="")
    password = quote(_required(env, "POSTGRES_PASSWORD"), safe="")
    host = env.get("ROLDA_POSTGRES_HOST", "127.0.0.1")
    port = _port(env, "ROLDA_POSTGRES_PORT", 5432)
    return f"postgresql://{user}:{password}@{host}:{port}/rolda"


def load_settings(env: Mapping[str, str]) -> Settings:
    """Build settings from environment variables."""
    pg_user = quote(_required(env, "POSTGRES_USER"), safe="")
    pg_password = quote(_required(env, "POSTGRES_PASSWORD"), safe="")
    pg_host = env.get("ROLDA_POSTGRES_HOST", "127.0.0.1")
    pg_port = _port(env, "ROLDA_POSTGRES_PORT", 5432)
    return Settings(
        clickhouse_host=env.get("ROLDA_CLICKHOUSE_HOST", "127.0.0.1"),
        clickhouse_port=_port(env, "ROLDA_CLICKHOUSE_PORT", 8123),
        clickhouse_user=_required(env, "CLICKHOUSE_USER"),
        clickhouse_password=_required(env, "CLICKHOUSE_PASSWORD"),
        postgres_dsn=(
            f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/rolda"
        ),
        window=timedelta(
            seconds=_minimum_int(env, "ROLDA_WINDOW_SECONDS", 1, 300)
        ),
        interval=timedelta(
            seconds=_minimum_int(env, "ROLDA_INTERVAL_SECONDS", 1, 60)
        ),
        max_catchup=timedelta(
            seconds=_minimum_int(env, "ROLDA_MAX_CATCHUP_SECONDS", 1, 86400)
        ),
        chunk=timedelta(
            seconds=_minimum_int(env, "ROLDA_CHUNK_SECONDS", 1, 3600)
        ),
        status_host=env.get("ROLDA_STATUS_HOST", "127.0.0.1"),
        status_port=_port(env, "ROLDA_STATUS_PORT", 9100),
        webhook_url=_optional_url(env, "ROLDA_WEBHOOK_URL"),
        slack_webhook_url=_optional_url(env, "ROLDA_SLACK_WEBHOOK_URL"),
        google_chat_webhook_url=_optional_url(
            env, "ROLDA_GOOGLE_CHAT_WEBHOOK_URL"
        ),
        teams_webhook_url=_optional_url(env, "ROLDA_TEAMS_WEBHOOK_URL"),
        detection=_detection(env),
    )


MIN_API_TOKEN_LENGTH = 16


@dataclass(frozen=True, slots=True)
class ApiSettings:
    """Settings of the HTTP API. The token is required."""

    token: str
    host: str = "127.0.0.1"
    port: int = 8000
    docs: bool = False


def _flag(env: Mapping[str, str], name: str) -> bool:
    raw = env.get(name)
    if raw is None:
        return False
    if raw.lower() in ("1", "true", "yes"):
        return True
    if raw.lower() in ("0", "false", "no"):
        return False
    msg = f"{name} must be true or false, got {raw!r}"
    raise SettingsError(msg)


def load_api_settings(env: Mapping[str, str]) -> ApiSettings:
    """Build the API settings. A short or missing token is an error."""
    token = _required(env, "ROLDA_API_TOKEN")
    if len(token) < MIN_API_TOKEN_LENGTH:
        msg = (
            f"ROLDA_API_TOKEN must have at least {MIN_API_TOKEN_LENGTH} "
            "characters"
        )
        raise SettingsError(msg)
    port = _number(env, "ROLDA_API_PORT", 8000)
    if not 1 <= port <= 65535:
        msg = f"ROLDA_API_PORT must be between 1 and 65535, got {port}"
        raise SettingsError(msg)
    return ApiSettings(
        token=token,
        host=env.get("ROLDA_API_HOST", "127.0.0.1"),
        port=port,
        docs=_flag(env, "ROLDA_API_DOCS"),
    )
