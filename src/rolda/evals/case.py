"""Eval case format: one JSON object per line, parsed strictly.

A case describes behavior only. Prompt and response content, tool
arguments and error messages are never part of it.
"""

import json
from dataclasses import dataclass
from typing import Any, Final

VERSION: Final = 1
LABELS: Final = frozenset({"failure", "false_alarm"})
EXPECTED: Final = frozenset({"incident", "no_incident"})


class EvalFormatError(ValueError):
    """Raised when a line is not a valid eval case."""


@dataclass(frozen=True, slots=True)
class EvalSpan:
    """The behavior of one span."""

    span_id: str
    parent_span_id: str | None
    name: str
    operation: str
    tool: str | None
    status: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ns: int


@dataclass(frozen=True, slots=True)
class EvalCase:
    """A labeled trace: what Rolda should or should not flag."""

    trace_id: str
    rule: str
    signature: str
    label: str
    expected: str
    spans: tuple[EvalSpan, ...]


_SPAN_FIELDS: Final = (
    "span_id",
    "parent_span_id",
    "name",
    "operation",
    "tool",
    "status",
    "input_tokens",
    "output_tokens",
    "duration_ns",
)
_CASE_FIELDS: Final = (
    "version",
    "trace_id",
    "rule",
    "signature",
    "label",
    "expected",
    "spans",
)


def to_line(case: EvalCase) -> str:
    """Serialize a case as one line of JSON."""
    data: dict[str, Any] = {
        "version": VERSION,
        "trace_id": case.trace_id,
        "rule": case.rule,
        "signature": case.signature,
        "label": case.label,
        "expected": case.expected,
        "spans": [
            {name: getattr(span, name) for name in _SPAN_FIELDS}
            for span in case.spans
        ],
    }
    return json.dumps(data, ensure_ascii=True, separators=(",", ":"))


def _exact_keys(data: dict[str, Any], fields: tuple[str, ...]) -> None:
    missing = [name for name in fields if name not in data]
    extra = sorted(set(data) - set(fields))
    if missing:
        msg = f"missing field: {missing[0]}"
        raise EvalFormatError(msg)
    if extra:
        msg = f"unexpected field: {extra[0]}"
        raise EvalFormatError(msg)


def _text(data: dict[str, Any], name: str, *, empty: bool = True) -> str:
    value = data[name]
    if not isinstance(value, str) or (not empty and not value):
        msg = f"invalid {name}"
        raise EvalFormatError(msg)
    return value


def _opt_text(data: dict[str, Any], name: str) -> str | None:
    value = data[name]
    if value is not None and not isinstance(value, str):
        msg = f"invalid {name}"
        raise EvalFormatError(msg)
    return value


def _opt_int(data: dict[str, Any], name: str) -> int | None:
    value = data[name]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        msg = f"invalid {name}"
        raise EvalFormatError(msg)
    return value


def _span(raw: object) -> EvalSpan:
    if not isinstance(raw, dict):
        msg = "invalid spans"
        raise EvalFormatError(msg)
    _exact_keys(raw, _SPAN_FIELDS)
    duration = _opt_int(raw, "duration_ns")
    if duration is None:
        msg = "invalid duration_ns"
        raise EvalFormatError(msg)
    return EvalSpan(
        span_id=_text(raw, "span_id", empty=False),
        parent_span_id=_opt_text(raw, "parent_span_id"),
        name=_text(raw, "name"),
        operation=_text(raw, "operation"),
        tool=_opt_text(raw, "tool"),
        status=_text(raw, "status"),
        input_tokens=_opt_int(raw, "input_tokens"),
        output_tokens=_opt_int(raw, "output_tokens"),
        duration_ns=duration,
    )


def _choice(data: dict[str, Any], name: str, allowed: frozenset[str]) -> str:
    value = _text(data, name)
    if value not in allowed:
        msg = f"invalid {name}"
        raise EvalFormatError(msg)
    return value


def parse_line(line: str) -> EvalCase:
    """Parse one line. Raise ``EvalFormatError`` on any deviation."""
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        msg = "not valid JSON"
        raise EvalFormatError(msg) from exc
    if not isinstance(data, dict):
        msg = "line is not a JSON object"
        raise EvalFormatError(msg)
    _exact_keys(data, _CASE_FIELDS)
    if data["version"] != VERSION or isinstance(data["version"], bool):
        msg = "unsupported version"
        raise EvalFormatError(msg)
    if not isinstance(data["spans"], list):
        msg = "invalid spans"
        raise EvalFormatError(msg)
    return EvalCase(
        trace_id=_text(data, "trace_id", empty=False),
        rule=_text(data, "rule", empty=False),
        signature=_text(data, "signature"),
        label=_choice(data, "label", LABELS),
        expected=_choice(data, "expected", EXPECTED),
        spans=tuple(_span(raw) for raw in data["spans"]),
    )
