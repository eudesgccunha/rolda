"""Tests for the trace aggregate."""

import json
from pathlib import Path

from rolda.traces import Trace, build_traces, normalize_span

FIXTURES = Path(__file__).parent / "fixtures"


def _traces() -> list[Trace]:
    rows = json.loads(
        (FIXTURES / "spans_genai.json").read_text(encoding="utf-8")
    )
    rows += json.loads(
        (FIXTURES / "spans_legacy.json").read_text(encoding="utf-8")
    )
    return build_traces(normalize_span(row) for row in rows)


def test_build_traces_groups_spans_by_trace_id() -> None:
    traces = _traces()

    assert sorted(len(trace.spans) for trace in traces) == [2, 3]


def test_trace_root_and_children() -> None:
    trace = next(t for t in _traces() if len(t.spans) == 3)

    assert trace.root.span_id == "b7ad6b7169203331"
    assert [s.span_id for s in trace.children("b7ad6b7169203331")] == [
        "00f067aa0ba902b7",
        "53995c3f42cd8ad8",
    ]
    assert trace.children("53995c3f42cd8ad8") == ()


def test_trace_spans_are_ordered_by_start_time() -> None:
    trace = next(t for t in _traces() if len(t.spans) == 3)

    starts = [span.started_at for span in trace.spans]
    assert starts == sorted(starts)
