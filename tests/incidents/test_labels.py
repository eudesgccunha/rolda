"""Tests for human and judge labels on incidents."""

import asyncio
from datetime import UTC, datetime

import pytest

from rolda.detection import Confidence
from rolda.incidents import (
    Incident,
    InMemoryIncidentStore,
    InMemoryLabelStore,
    Label,
    LabelSource,
    UnknownIncidentError,
)
from rolda.judge import Verdict

NOW = datetime(2026, 11, 26, 12, tzinfo=UTC)


def _incident(trace_id: str = "t1", rule: str = "span_error") -> Incident:
    return Incident(
        trace_id=trace_id,
        rule=rule,
        span_id="s1",
        evidence="boom",
        confidence=Confidence.HIGH,
        signature="a|span_error|tool|boom",
        path=("root", "tool"),
        detected_at=NOW,
    )


def _label(
    verdict: Verdict = Verdict.FAILURE,
    source: LabelSource = LabelSource.HUMAN,
    trace_id: str = "t1",
) -> Label:
    return Label(
        trace_id=trace_id,
        rule="span_error",
        source=source,
        verdict=verdict,
        reason="checked by hand",
        labeler="ana",
        labeled_at=NOW,
    )


def _stores() -> tuple[InMemoryIncidentStore, InMemoryLabelStore]:
    incidents = InMemoryIncidentStore()
    asyncio.run(incidents.save(_incident()))
    return incidents, InMemoryLabelStore(incidents)


def test_label_for_unknown_incident_is_rejected() -> None:
    _, labels = _stores()

    with pytest.raises(UnknownIncidentError):
        asyncio.run(labels.upsert(_label(trace_id="ghost")))


def test_relabeling_replaces_the_previous_label() -> None:
    _, labels = _stores()

    asyncio.run(labels.upsert(_label(Verdict.FAILURE)))
    asyncio.run(labels.upsert(_label(Verdict.FALSE_ALARM)))

    [(_, label)] = asyncio.run(labels.labeled(LabelSource.HUMAN))
    assert label.verdict is Verdict.FALSE_ALARM


def test_human_and_judge_labels_are_kept_apart() -> None:
    _, labels = _stores()

    asyncio.run(labels.upsert(_label(Verdict.FAILURE, LabelSource.HUMAN)))
    asyncio.run(labels.upsert(_label(Verdict.UNCERTAIN, LabelSource.JUDGE)))

    human = asyncio.run(labels.labeled(LabelSource.HUMAN))
    judge = asyncio.run(labels.labeled(LabelSource.JUDGE))
    assert [label.verdict for _, label in human] == [Verdict.FAILURE]
    assert [label.verdict for _, label in judge] == [Verdict.UNCERTAIN]


def test_labeled_returns_the_incident_with_its_label() -> None:
    _, labels = _stores()
    asyncio.run(labels.upsert(_label()))

    [(incident, label)] = asyncio.run(labels.labeled(LabelSource.HUMAN))

    assert incident.signature == "a|span_error|tool|boom"
    assert label.labeler == "ana"


def test_for_trace_returns_labels_of_every_source() -> None:
    _, labels = _stores()
    asyncio.run(labels.upsert(_label(Verdict.FAILURE, LabelSource.HUMAN)))
    asyncio.run(labels.upsert(_label(Verdict.UNCERTAIN, LabelSource.JUDGE)))

    result = asyncio.run(labels.for_trace("t1"))

    assert {label.source for label in result} == {
        LabelSource.HUMAN,
        LabelSource.JUDGE,
    }
    assert asyncio.run(labels.for_trace("other")) == []
