"""Tests for building eval cases from labeled incidents."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rolda.detection import Confidence
from rolda.entrypoints.cli import main
from rolda.evals import build_cases, parse_line, to_line
from rolda.incidents import (
    Incident,
    InMemoryIncidentStore,
    InMemoryLabelStore,
    Label,
    LabelSource,
)
from rolda.judge import Verdict
from rolda.traces import InMemorySpanSource, Operation, Span, SpanStatus

SpanFactory = Callable[..., Span]
NOW = datetime(2026, 11, 26, 12, tzinfo=UTC)
GOLDEN = Path(__file__).parent / "golden.jsonl"


def _incident(trace_id: str, rule: str = "span_error") -> Incident:
    return Incident(
        trace_id=trace_id,
        rule=rule,
        span_id="tool",
        evidence="boom",
        confidence=Confidence.HIGH,
        signature="agent-a|span_error|tool|boom",
        path=("root", "tool"),
        detected_at=NOW,
    )


def _label(trace_id: str, verdict: Verdict, rule: str = "span_error") -> Label:
    return Label(
        trace_id=trace_id,
        rule=rule,
        source=LabelSource.HUMAN,
        verdict=verdict,
        reason="",
        labeler="ana",
        labeled_at=NOW,
    )


def _world(
    make_span: SpanFactory, verdicts: dict[str, Verdict]
) -> tuple[InMemoryLabelStore, InMemorySpanSource]:
    incidents = InMemoryIncidentStore()
    spans = InMemorySpanSource()
    labels = InMemoryLabelStore(incidents)
    for trace_id, verdict in verdicts.items():
        asyncio.run(incidents.save(_incident(trace_id)))
        asyncio.run(labels.upsert(_label(trace_id, verdict)))
        spans.add(
            make_span(
                "root",
                trace_id=trace_id,
                operation=Operation.AGENT,
            )
        )
        spans.add(
            make_span(
                "tool",
                trace_id=trace_id,
                parent="root",
                operation=Operation.TOOL,
                start_s=1,
                status=SpanStatus.ERROR,
                tool_name="search",
                tool_arguments="SECRET ARGUMENTS",
            )
        )
    return labels, spans


def test_failure_and_false_alarm_are_exported_uncertain_is_not(
    make_span: SpanFactory,
) -> None:
    labels, spans = _world(
        make_span,
        {
            "t-fail": Verdict.FAILURE,
            "t-fine": Verdict.FALSE_ALARM,
            "t-unsure": Verdict.UNCERTAIN,
        },
    )

    cases = asyncio.run(build_cases(labels, spans))

    assert {c.trace_id: (c.label, c.expected) for c in cases} == {
        "t-fail": ("failure", "incident"),
        "t-fine": ("false_alarm", "no_incident"),
    }


def test_case_has_behavior_but_no_tool_arguments(
    make_span: SpanFactory,
) -> None:
    labels, spans = _world(make_span, {"t1": Verdict.FAILURE})

    [case] = asyncio.run(build_cases(labels, spans))

    assert [s.span_id for s in case.spans] == ["root", "tool"]
    assert case.spans[1].tool == "search"
    assert case.spans[1].status == "error"
    assert "SECRET" not in repr(case)


def test_trace_without_spans_is_skipped(make_span: SpanFactory) -> None:
    labels, _ = _world(make_span, {"t1": Verdict.FAILURE})

    assert asyncio.run(build_cases(labels, InMemorySpanSource())) == []


def test_export_matches_the_golden_file(make_span: SpanFactory) -> None:
    labels, spans = _world(make_span, {"t1": Verdict.FAILURE})

    [case] = asyncio.run(build_cases(labels, spans))

    assert to_line(case) + "\n" == GOLDEN.read_text(encoding="utf-8")


def test_export_command_writes_a_private_file(
    make_span: SpanFactory, tmp_path: Path
) -> None:
    labels, spans = _world(make_span, {"t1": Verdict.FAILURE})
    out = tmp_path / "evals.jsonl"

    code = main(
        ["export-evals", "--out", str(out)],
        label_store=labels,
        span_source=spans,
    )

    assert code == 0
    assert out.stat().st_mode & 0o777 == 0o600
    [line] = out.read_text(encoding="utf-8").splitlines()
    assert parse_line(line).trace_id == "t1"


def test_export_command_refuses_to_overwrite(
    make_span: SpanFactory,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    labels, spans = _world(make_span, {"t1": Verdict.FAILURE})
    out = tmp_path / "evals.jsonl"
    out.write_text("keep me", encoding="utf-8")

    code = main(
        ["export-evals", "--out", str(out)],
        label_store=labels,
        span_source=spans,
    )

    assert code == 1
    assert out.read_text(encoding="utf-8") == "keep me"
    assert "--force" in capsys.readouterr().err


def test_export_command_force_overwrites(
    make_span: SpanFactory, tmp_path: Path
) -> None:
    labels, spans = _world(make_span, {"t1": Verdict.FAILURE})
    out = tmp_path / "evals.jsonl"
    out.write_text("old", encoding="utf-8")

    code = main(
        ["export-evals", "--out", str(out), "--force"],
        label_store=labels,
        span_source=spans,
    )

    assert code == 0
    assert out.read_text(encoding="utf-8") != "old"
    assert out.stat().st_mode & 0o777 == 0o600
