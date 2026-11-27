"""Entry points report a bad environment cleanly, without a traceback."""

import pytest

from rolda.entrypoints import __main__ as worker_main
from rolda.entrypoints import api_main


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "CLICKHOUSE_USER",
        "CLICKHOUSE_PASSWORD",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "ROLDA_API_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)


def test_api_without_a_token_exits_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clear(monkeypatch)
    for name in ("CLICKHOUSE_USER", "CLICKHOUSE_PASSWORD"):
        monkeypatch.setenv(name, "x")
    for name in ("POSTGRES_USER", "POSTGRES_PASSWORD"):
        monkeypatch.setenv(name, "x")

    with pytest.raises(SystemExit) as exit_info:
        api_main.main()

    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert "ROLDA_API_TOKEN" in err
    assert "Traceback" not in err


def test_worker_without_credentials_exits_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clear(monkeypatch)

    with pytest.raises(SystemExit) as exit_info:
        worker_main.main()

    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert "CLICKHOUSE_USER" in err or "POSTGRES_USER" in err
    assert "Traceback" not in err
