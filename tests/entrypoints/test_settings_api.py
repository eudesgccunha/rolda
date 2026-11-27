"""Tests for the API settings."""

import pytest

from rolda.entrypoints.settings import SettingsError, load_api_settings

TOKEN = "a-long-enough-test-token"  # noqa: S105 - fake token for tests


def test_defaults_bind_to_loopback_without_docs() -> None:
    settings = load_api_settings({"ROLDA_API_TOKEN": TOKEN})

    assert settings.token == TOKEN
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.docs is False


def test_values_can_be_overridden() -> None:
    settings = load_api_settings(
        {
            "ROLDA_API_TOKEN": TOKEN,
            "ROLDA_API_HOST": "0.0.0.0",  # noqa: S104 - test value only
            "ROLDA_API_PORT": "9000",
            "ROLDA_API_DOCS": "true",
        }
    )

    assert settings.host == "0.0.0.0"  # noqa: S104 - test value only
    assert settings.port == 9000
    assert settings.docs is True


def test_the_token_is_required() -> None:
    with pytest.raises(SettingsError, match="ROLDA_API_TOKEN"):
        load_api_settings({})


def test_a_short_token_is_refused() -> None:
    with pytest.raises(SettingsError, match="ROLDA_API_TOKEN"):
        load_api_settings({"ROLDA_API_TOKEN": "short"})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ROLDA_API_PORT", "0"),
        ("ROLDA_API_PORT", "70000"),
        ("ROLDA_API_PORT", "http"),
        ("ROLDA_API_DOCS", "maybe"),
    ],
)
def test_invalid_values_are_refused(name: str, value: str) -> None:
    with pytest.raises(SettingsError, match=name):
        load_api_settings({"ROLDA_API_TOKEN": TOKEN, name: value})
