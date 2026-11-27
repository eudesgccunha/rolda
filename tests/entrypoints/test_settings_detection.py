"""Tests for detection thresholds read from the environment."""

import pytest

from rolda.detection import DetectionConfig
from rolda.entrypoints.settings import SettingsError, load_settings

ENV = {
    "CLICKHOUSE_USER": "u",
    "CLICKHOUSE_PASSWORD": "p",
    "POSTGRES_USER": "pu",
    "POSTGRES_PASSWORD": "pp",
}


def test_defaults_are_the_calibrated_config() -> None:
    assert load_settings(ENV).detection == DetectionConfig()


def test_each_threshold_can_be_set() -> None:
    settings = load_settings(
        {
            **ENV,
            "ROLDA_Z_THRESHOLD": "4.5",
            "ROLDA_Z_LATENCY": "3.1",
            "ROLDA_Z_SPAN_LATENCY": "2.9",
            "ROLDA_Z_TOKENS": "2.2",
            "ROLDA_MIN_SAMPLES": "50",
            "ROLDA_TOOL_LOOP_REPEATS": "5",
        }
    )

    detection = settings.detection
    assert detection.z_threshold == 4.5
    assert detection.latency_z == 3.1
    assert detection.span_latency_z == 2.9
    assert detection.token_z == 2.2
    assert detection.min_samples == 50
    assert detection.tool_loop_repeats == 5


def test_unset_values_keep_their_defaults() -> None:
    settings = load_settings({**ENV, "ROLDA_Z_TOKENS": "2.0"})

    assert settings.detection.token_z == 2.0
    assert settings.detection.span_latency_z == 3.0
    assert settings.detection.min_samples == 30


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ROLDA_Z_THRESHOLD", "high"),
        ("ROLDA_Z_TOKENS", "nan"),
        ("ROLDA_Z_LATENCY", "inf"),
        ("ROLDA_Z_SPAN_LATENCY", "0"),
        ("ROLDA_Z_TOKENS", "-1"),
        ("ROLDA_MIN_SAMPLES", "0"),
        ("ROLDA_MIN_SAMPLES", "3.5"),
        ("ROLDA_TOOL_LOOP_REPEATS", "1"),
    ],
)
def test_invalid_values_are_an_error(name: str, value: str) -> None:
    with pytest.raises(SettingsError, match=name):
        load_settings({**ENV, name: value})
