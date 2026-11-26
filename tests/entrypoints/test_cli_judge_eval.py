"""Tests for the judge-eval command."""

from pathlib import Path

import pytest

from rolda.entrypoints.cli import main
from rolda.evals import EvalCase, EvalSpan, to_line
from rolda.judge import Finding, Judgement, Verdict


class _AlwaysFailure:
    async def evaluate(self, finding: Finding) -> Judgement:
        return Judgement(Verdict.FAILURE, "r")


def _case(index: int) -> EvalCase:
    label = "failure" if index % 2 == 0 else "false_alarm"
    return EvalCase(
        trace_id=f"t{index}",
        rule="span_error",
        signature="a|span_error|tool|boom",
        label=label,
        expected="incident" if label == "failure" else "no_incident",
        spans=(
            EvalSpan(
                span_id="s",
                parent_span_id=None,
                name="root",
                operation="agent",
                tool=None,
                status="error",
                input_tokens=None,
                output_tokens=None,
                duration_ns=1,
            ),
        ),
    )


def _write(path: Path, count: int) -> Path:
    path.write_text(
        "".join(to_line(_case(i)) + "\n" for i in range(count)),
        encoding="utf-8",
    )
    return path


def test_prints_kappa_and_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    evals = _write(tmp_path / "e.jsonl", 6)

    code = main(
        ["judge-eval", "--evals", str(evals), "--min-cases", "4"],
        judge=_AlwaysFailure(),
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "kappa" in out
    assert "scored: 6" in out
    assert "uncertain: 0" in out


def test_refuses_with_too_few_cases(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    evals = _write(tmp_path / "e.jsonl", 6)

    code = main(["judge-eval", "--evals", str(evals)], judge=_AlwaysFailure())

    assert code == 1
    assert "30" in capsys.readouterr().err


def test_invalid_line_is_reported_with_its_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    evals = tmp_path / "e.jsonl"
    evals.write_text(to_line(_case(0)) + "\nnot json\n", encoding="utf-8")

    code = main(
        ["judge-eval", "--evals", str(evals), "--min-cases", "1"],
        judge=_AlwaysFailure(),
    )

    assert code == 1
    assert "line 2" in capsys.readouterr().err


def test_missing_api_key_is_a_clear_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    evals = _write(tmp_path / "e.jsonl", 6)

    code = main(["judge-eval", "--evals", str(evals), "--min-cases", "1"])

    assert code == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
