"""Tests for the eval case format (strict JSONL)."""

import json
from typing import Any

import pytest

from rolda.evals import (
    EvalCase,
    EvalFormatError,
    EvalSpan,
    parse_line,
    to_line,
)


def _case(**overrides: Any) -> EvalCase:
    values: dict[str, Any] = {
        "trace_id": "t1",
        "rule": "span_error",
        "signature": "a|span_error|tool|boom",
        "label": "failure",
        "expected": "incident",
        "spans": (
            EvalSpan(
                span_id="s1",
                parent_span_id=None,
                name="root",
                operation="agent",
                tool=None,
                status="ok",
                input_tokens=None,
                output_tokens=None,
                duration_ns=10,
            ),
            EvalSpan(
                span_id="s2",
                parent_span_id="s1",
                name="tool",
                operation="tool",
                tool="search",
                status="error",
                input_tokens=3,
                output_tokens=4,
                duration_ns=5,
            ),
        ),
    }
    values.update(overrides)
    return EvalCase(**values)


def test_line_round_trips() -> None:
    case = _case()

    assert parse_line(to_line(case)) == case


def test_line_is_one_line_of_json_with_a_version() -> None:
    line = to_line(_case())

    assert "\n" not in line
    assert json.loads(line)["version"] == 1


def test_hostile_content_stays_a_json_string() -> None:
    hostile = 'x"}\n{"version": 1, "evil": true}'
    case = _case(signature=hostile)

    line = to_line(case)

    assert "\n" not in line
    assert parse_line(line).signature == hostile


def _data() -> dict[str, Any]:
    result: dict[str, Any] = json.loads(to_line(_case()))
    return result


def test_missing_field_is_rejected() -> None:
    data = _data()
    del data["rule"]

    with pytest.raises(EvalFormatError, match="rule"):
        parse_line(json.dumps(data))


def test_extra_field_is_rejected() -> None:
    data = _data()
    data["prompt"] = "secret"

    with pytest.raises(EvalFormatError, match="prompt"):
        parse_line(json.dumps(data))


def test_extra_span_field_is_rejected() -> None:
    data = _data()
    data["spans"][0]["response"] = "secret"

    with pytest.raises(EvalFormatError, match="response"):
        parse_line(json.dumps(data))


def test_wrong_type_is_rejected() -> None:
    data = _data()
    data["spans"][1]["duration_ns"] = "5"

    with pytest.raises(EvalFormatError, match="duration_ns"):
        parse_line(json.dumps(data))


def test_bool_is_not_an_integer() -> None:
    data = _data()
    data["spans"][1]["duration_ns"] = True

    with pytest.raises(EvalFormatError, match="duration_ns"):
        parse_line(json.dumps(data))


def test_unknown_version_is_rejected() -> None:
    data = _data()
    data["version"] = 2

    with pytest.raises(EvalFormatError, match="version"):
        parse_line(json.dumps(data))


@pytest.mark.parametrize(
    ("field", "value"),
    [("label", "maybe"), ("expected", "perhaps"), ("rule", "")],
)
def test_bad_values_are_rejected(field: str, value: str) -> None:
    data = _data()
    data[field] = value

    with pytest.raises(EvalFormatError, match=field):
        parse_line(json.dumps(data))


@pytest.mark.parametrize("line", ["", "not json", "[]", "42"])
def test_non_object_lines_are_rejected(line: str) -> None:
    with pytest.raises(EvalFormatError):
        parse_line(line)
