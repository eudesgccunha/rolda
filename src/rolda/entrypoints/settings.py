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
    )


def _optional_url(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        msg = f"{name} must be an http or https URL with a host"
        raise SettingsError(msg)
    return value


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
        webhook_url=_optional_url(env, "ROLDA_WEBHOOK_URL"),
        slack_webhook_url=_optional_url(env, "ROLDA_SLACK_WEBHOOK_URL"),
        google_chat_webhook_url=_optional_url(
            env, "ROLDA_GOOGLE_CHAT_WEBHOOK_URL"
        ),
        teams_webhook_url=_optional_url(env, "ROLDA_TEAMS_WEBHOOK_URL"),
        detection=_detection(env),
    )
