"""The label and export commands read only what they need."""

import pytest

from rolda.entrypoints import cli


def _only_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("CLICKHOUSE_USER", "CLICKHOUSE_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")


def test_label_store_needs_only_postgres_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _only_postgres(monkeypatch)

    assert cli._default_label_store() is not None


def test_missing_database_variables_exit_cleanly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("POSTGRES_USER", "POSTGRES_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    code = cli.main(["label", "t1", "span_error", "failure"])

    assert code == 2
    err = capsys.readouterr().err
    assert "POSTGRES_USER" in err
    assert "Traceback" not in err
