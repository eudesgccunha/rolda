"""Tests for settings loading and the worker loop."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from rolda.entrypoints.settings import Settings, SettingsError, load_settings
from rolda.entrypoints.worker import WindowResult, serve

ENV = {
    "CLICKHOUSE_USER": "u",
    "CLICKHOUSE_PASSWORD": "p",
    "POSTGRES_USER": "pu",
    "POSTGRES_PASSWORD": "pp",
}


def test_settings_use_defaults_and_environment() -> None:
    settings = load_settings(ENV)

    assert settings.clickhouse_host == "127.0.0.1"
    assert settings.clickhouse_port == 8123
    assert settings.postgres_dsn == ("postgresql://pu:pp@127.0.0.1:5432/rolda")
    assert settings.window == timedelta(minutes=5)
    assert settings.interval == timedelta(seconds=60)


def test_settings_accept_overrides() -> None:
    settings = load_settings(
        {
            **ENV,
            "ROLDA_POSTGRES_HOST": "db",
            "ROLDA_WINDOW_SECONDS": "120",
            "ROLDA_INTERVAL_SECONDS": "10",
        }
    )

    assert "@db:5432" in settings.postgres_dsn
    assert settings.window == timedelta(seconds=120)
    assert settings.interval == timedelta(seconds=10)


def test_settings_quote_special_characters_in_credentials() -> None:
    settings = load_settings({**ENV, "POSTGRES_PASSWORD": "a/b@c:d"})

    assert "a%2Fb%40c%3Ad" in settings.postgres_dsn


@pytest.mark.parametrize("missing", sorted(ENV))
def test_missing_credential_is_an_error(missing: str) -> None:
    env = {k: v for k, v in ENV.items() if k != missing}

    with pytest.raises(SettingsError, match=missing):
        load_settings(env)


def test_non_numeric_value_is_an_error() -> None:
    with pytest.raises(SettingsError, match="ROLDA_WINDOW_SECONDS"):
        load_settings({**ENV, "ROLDA_WINDOW_SECONDS": "soon"})


class _FakeWorker:
    def __init__(self) -> None:
        self.windows: list[tuple[datetime, datetime]] = []

    async def run_window(self, start: datetime, end: datetime) -> WindowResult:
        self.windows.append((start, end))
        return WindowResult(traces=0, findings=0, new_incidents=0)


def test_serve_runs_contiguous_windows() -> None:
    clock_values = iter(
        datetime(2026, 11, 26, 10, m, tzinfo=UTC) for m in (5, 6, 7)
    )
    worker = _FakeWorker()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    settings: Settings = load_settings(ENV)
    asyncio.run(
        serve(
            worker,
            settings,
            clock=lambda: next(clock_values),
            sleep=fake_sleep,
            iterations=3,
        )
    )

    assert worker.windows[0][0] == datetime(2026, 11, 26, 10, 0, tzinfo=UTC)
    for (_, end), (start, _) in zip(
        worker.windows, worker.windows[1:], strict=False
    ):
        assert start == end
    assert sleeps == [60.0, 60.0, 60.0]


def test_webhook_urls_are_optional_and_validated() -> None:
    assert load_settings(ENV).webhook_url is None
    assert load_settings(ENV).slack_webhook_url is None

    settings = load_settings(
        {
            **ENV,
            "ROLDA_WEBHOOK_URL": "https://hooks.example.com/a",
            "ROLDA_SLACK_WEBHOOK_URL": "https://hooks.slack.com/b",
        }
    )

    assert settings.webhook_url == "https://hooks.example.com/a"
    assert settings.slack_webhook_url == "https://hooks.slack.com/b"


def test_invalid_webhook_url_is_an_error() -> None:
    with pytest.raises(SettingsError, match="ROLDA_WEBHOOK_URL"):
        load_settings({**ENV, "ROLDA_WEBHOOK_URL": "ftp://x/y"})


def test_chat_and_teams_urls_are_optional_and_validated() -> None:
    assert load_settings(ENV).google_chat_webhook_url is None
    assert load_settings(ENV).teams_webhook_url is None

    settings = load_settings(
        {
            **ENV,
            "ROLDA_GOOGLE_CHAT_WEBHOOK_URL": "https://chat.example/x",
            "ROLDA_TEAMS_WEBHOOK_URL": "https://teams.example/y",
        }
    )

    assert settings.google_chat_webhook_url == "https://chat.example/x"
    assert settings.teams_webhook_url == "https://teams.example/y"


@pytest.mark.parametrize(
    "name",
    ["ROLDA_GOOGLE_CHAT_WEBHOOK_URL", "ROLDA_TEAMS_WEBHOOK_URL"],
)
def test_invalid_chat_or_teams_url_is_an_error(name: str) -> None:
    with pytest.raises(SettingsError, match=name):
        load_settings({**ENV, name: "file:///etc/passwd"})
