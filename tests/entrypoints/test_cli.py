"""Tests for the command line."""

import asyncio
from datetime import UTC, datetime

import pytest

from rolda.detection import Confidence
from rolda.entrypoints.cli import main
from rolda.incidents import (
    Incident,
    InMemoryIncidentStore,
    InMemoryLabelStore,
    LabelSource,
)
from rolda.judge import Verdict

NOW = datetime(2026, 11, 26, 12, tzinfo=UTC)


def _stores() -> tuple[InMemoryIncidentStore, InMemoryLabelStore]:
    incidents = InMemoryIncidentStore()
    asyncio.run(
        incidents.save(
            Incident(
                trace_id="t1",
                rule="span_error",
                span_id="s1",
                evidence="boom",
                confidence=Confidence.HIGH,
                signature="a|span_error|tool|boom",
                path=("root", "tool"),
                detected_at=NOW,
            )
        )
    )
    return incidents, InMemoryLabelStore(incidents)


def test_label_command_stores_a_human_label(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, labels = _stores()

    code = main(
        [
            "label",
            "t1",
            "span_error",
            "failure",
            "--reason",
            "real outage",
            "--labeler",
            "ana",
        ],
        label_store=labels,
        clock=lambda: NOW,
    )

    [(_, label)] = asyncio.run(labels.labeled(LabelSource.HUMAN))
    assert code == 0
    assert label.verdict is Verdict.FAILURE
    assert label.reason == "real outage"
    assert label.labeler == "ana"
    assert label.labeled_at == NOW
    assert "t1" in capsys.readouterr().out


def test_label_command_reports_an_unknown_incident(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, labels = _stores()

    code = main(
        ["label", "ghost", "span_error", "failure"],
        label_store=labels,
        clock=lambda: NOW,
    )

    assert code == 1
    assert "no incident" in capsys.readouterr().err


def test_label_command_rejects_an_unknown_verdict() -> None:
    _, labels = _stores()

    with pytest.raises(SystemExit) as exit_info:
        main(
            ["label", "t1", "span_error", "maybe"],
            label_store=labels,
            clock=lambda: NOW,
        )

    assert exit_info.value.code == 2
