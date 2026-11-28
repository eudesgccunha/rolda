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


@pytest.mark.parametrize("blank", ["", " ", "   ", "\t", " \n "])
def test_blank_webhook_values_count_as_not_configured(blank: str) -> None:
    settings = load_settings(
        {
            **ENV,
            "ROLDA_WEBHOOK_URL": blank,
            "ROLDA_SLACK_WEBHOOK_URL": blank,
            "ROLDA_GOOGLE_CHAT_WEBHOOK_URL": blank,
            "ROLDA_TEAMS_WEBHOOK_URL": blank,
        }
    )

    assert settings.webhook_url is None
    assert settings.slack_webhook_url is None
    assert settings.google_chat_webhook_url is None
    assert settings.teams_webhook_url is None


def test_webhook_url_is_trimmed() -> None:
    settings = load_settings(
        {**ENV, "ROLDA_WEBHOOK_URL": "  https://hooks.example.com/a \n"}
    )

    assert settings.webhook_url == "https://hooks.example.com/a"


def test_a_bad_webhook_port_is_a_settings_error() -> None:
    with pytest.raises(SettingsError, match="ROLDA_SLACK_WEBHOOK_URL"):
        load_settings({**ENV, "ROLDA_SLACK_WEBHOOK_URL": "http://h:80a/x"})


@pytest.mark.parametrize(
    "name", ["ROLDA_WINDOW_SECONDS", "ROLDA_INTERVAL_SECONDS"]
)
@pytest.mark.parametrize("value", ["0", "-5"])
def test_window_and_interval_must_be_positive(name: str, value: str) -> None:
    with pytest.raises(SettingsError, match=name):
        load_settings({**ENV, name: value})


@pytest.mark.parametrize(
    "name",
    [
        "ROLDA_CLICKHOUSE_PORT",
        "ROLDA_POSTGRES_PORT",
    ],
)
@pytest.mark.parametrize("value", ["0", "70000"])
def test_database_ports_must_be_valid(name: str, value: str) -> None:
    with pytest.raises(SettingsError, match=name):
        load_settings({**ENV, name: value})


class _FlakyWorker:
    """Fails on the first call, then works."""

    def __init__(self, failures: int) -> None:
        self._failures = failures
        self.windows: list[tuple[datetime, datetime]] = []

    async def run_window(self, start: datetime, end: datetime) -> WindowResult:
        self.windows.append((start, end))
        if len(self.windows) <= self._failures:
            msg = "database is down"
            raise ConnectionError(msg)
        return WindowResult(traces=0, findings=0, new_incidents=0)


def test_serve_retries_the_same_window_after_an_error() -> None:
    clock_values = iter(
        datetime(2026, 11, 26, 10, m, tzinfo=UTC) for m in (5, 6, 7)
    )
    worker = _FlakyWorker(failures=1)

    async def no_sleep(seconds: float) -> None:
        del seconds

    asyncio.run(
        serve(
            worker,
            load_settings(ENV),
            clock=lambda: next(clock_values),
            sleep=no_sleep,
            iterations=3,
        )
    )

    first, retry, after = worker.windows
    assert retry[0] == first[0]
    assert after[0] == retry[1]


def test_status_server_defaults_to_loopback() -> None:
    settings = load_settings(ENV)

    assert (settings.status_host, settings.status_port) == ("127.0.0.1", 9100)


def test_status_server_can_be_moved() -> None:
    settings = load_settings(
        {**ENV, "ROLDA_STATUS_HOST": "0.0.0.0", "ROLDA_STATUS_PORT": "9200"}  # noqa: S104 - test value
    )

    assert (settings.status_host, settings.status_port) == ("0.0.0.0", 9200)  # noqa: S104 - test value


@pytest.mark.parametrize("value", ["0", "70000", "http"])
def test_status_port_must_be_valid(value: str) -> None:
    with pytest.raises(SettingsError, match="ROLDA_STATUS_PORT"):
        load_settings({**ENV, "ROLDA_STATUS_PORT": value})


def test_the_database_pool_has_a_default_size_and_can_change() -> None:
    assert load_settings(ENV).postgres_pool_size == 5
    settings = load_settings({**ENV, "ROLDA_POSTGRES_POOL_SIZE": "12"})

    assert settings.postgres_pool_size == 12


@pytest.mark.parametrize("value", ["0", "-1", "many"])
def test_the_pool_size_must_be_positive(value: str) -> None:
    with pytest.raises(SettingsError, match="ROLDA_POSTGRES_POOL_SIZE"):
        load_settings({**ENV, "ROLDA_POSTGRES_POOL_SIZE": value})


def test_by_default_one_worker_owns_everything() -> None:
    settings = load_settings(ENV)

    assert (settings.shard_count, settings.shard_index) == (1, 0)


def test_the_shard_can_be_set() -> None:
    settings = load_settings(
        {**ENV, "ROLDA_SHARD_COUNT": "4", "ROLDA_SHARD_INDEX": "2"}
    )

    assert (settings.shard_count, settings.shard_index) == (4, 2)


def test_the_shard_index_can_come_from_the_pod_ordinal() -> None:
    settings = load_settings(
        {
            **ENV,
            "ROLDA_SHARD_COUNT": "3",
            "ROLDA_SHARD_INDEX": "auto",
            "HOSTNAME": "rolda-worker-2",
        }
    )

    assert settings.shard_index == 2


@pytest.mark.parametrize(
    "extra",
    [
        {"ROLDA_SHARD_COUNT": "0"},
        {"ROLDA_SHARD_COUNT": "3", "ROLDA_SHARD_INDEX": "3"},
        {"ROLDA_SHARD_COUNT": "3", "ROLDA_SHARD_INDEX": "-1"},
        {"ROLDA_SHARD_COUNT": "3", "ROLDA_SHARD_INDEX": "auto"},
        {
            "ROLDA_SHARD_COUNT": "3",
            "ROLDA_SHARD_INDEX": "auto",
            "HOSTNAME": "no-number",
        },
        {
            "ROLDA_SHARD_COUNT": "2",
            "ROLDA_SHARD_INDEX": "auto",
            "HOSTNAME": "rolda-worker-5",
        },
    ],
)
def test_an_invalid_shard_stops_the_worker_at_start(
    extra: dict[str, str],
) -> None:
    with pytest.raises(SettingsError, match="ROLDA_SHARD"):
        load_settings({**ENV, **extra})
