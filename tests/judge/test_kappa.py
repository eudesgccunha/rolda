"""Tests for Cohen's kappa and the judge evaluation report."""

import asyncio
from collections.abc import Sequence

import pytest

from rolda.evals import EvalCase, EvalSpan
from rolda.judge import Finding, Judgement, Verdict
from rolda.judge.evaluate import (
    InsufficientCasesError,
    evaluate_judge,
)
from rolda.judge.kappa import cohen_kappa


def test_perfect_agreement_is_one() -> None:
    labels = ["a", "b", "a", "b"]

    assert cohen_kappa(labels, labels) == 1.0


def test_chance_agreement_is_zero() -> None:
    first = ["a", "a", "b", "b"]
    second = ["a", "b", "a", "b"]

    assert cohen_kappa(first, second) == 0.0


def test_known_value() -> None:
    # 20 a/a, 5 a/b, 10 b/a, 15 b/b: po=0.7, pe=0.5 -> kappa=0.4
    first = ["a"] * 25 + ["b"] * 25
    second = ["a"] * 20 + ["b"] * 5 + ["a"] * 10 + ["b"] * 15

    assert cohen_kappa(first, second) == pytest.approx(0.4)


def test_systematic_disagreement_is_negative() -> None:
    assert cohen_kappa(["a", "b"], ["b", "a"]) < 0


def test_single_label_everywhere_counts_as_agreement() -> None:
    assert cohen_kappa(["a", "a"], ["a", "a"]) == 1.0


def test_empty_or_unequal_input_is_an_error() -> None:
    with pytest.raises(ValueError, match="empty"):
        cohen_kappa([], [])
    with pytest.raises(ValueError, match="same length"):
        cohen_kappa(["a"], ["a", "b"])


def _case(trace_id: str, label: str) -> EvalCase:
    span = EvalSpan(
        span_id="s",
        parent_span_id=None,
        name="root",
        operation="agent",
        tool=None,
        status="error",
        input_tokens=None,
        output_tokens=None,
        duration_ns=1,
    )
    expected = "incident" if label == "failure" else "no_incident"
    return EvalCase(
        trace_id=trace_id,
        rule="span_error",
        signature="a|span_error|agent|boom",
        label=label,
        expected=expected,
        spans=(span,),
    )


class _ScriptedJudge:
    """Judge that answers from a table; records what it was shown."""

    def __init__(self, answers: dict[str, Verdict]) -> None:
        self._answers = answers
        self.seen: list[Finding] = []

    async def evaluate(self, finding: Finding) -> Judgement:
        self.seen.append(finding)
        return Judgement(self._answers[finding.trace_id], "r")


def _cases(count: int) -> Sequence[EvalCase]:
    return [
        _case(f"t{i}", "failure" if i % 2 == 0 else "false_alarm")
        for i in range(count)
    ]


def test_report_scores_agreement_and_counts_uncertain() -> None:
    cases = _cases(6)
    answers = {
        "t0": Verdict.FAILURE,
        "t1": Verdict.FALSE_ALARM,
        "t2": Verdict.FAILURE,
        "t3": Verdict.FALSE_ALARM,
        "t4": Verdict.UNCERTAIN,
        "t5": Verdict.FAILURE,
    }

    report = asyncio.run(
        evaluate_judge(_ScriptedJudge(answers), cases, min_cases=4)
    )

    assert report.scored == 5
    assert report.uncertain == 1
    assert report.agreement == pytest.approx(0.8)
    assert report.confusion[("failure", "failure")] == 2
    assert report.confusion[("false_alarm", "failure")] == 1
    assert 0 < report.kappa < 1


def test_too_few_cases_is_refused() -> None:
    with pytest.raises(InsufficientCasesError, match="30"):
        asyncio.run(
            evaluate_judge(_ScriptedJudge({}), _cases(5), min_cases=30)
        )


def test_judge_sees_behavior_not_the_human_label() -> None:
    cases = _cases(2)
    judge = _ScriptedJudge({"t0": Verdict.FAILURE, "t1": Verdict.FAILURE})

    asyncio.run(evaluate_judge(judge, cases, min_cases=1))

    for finding in judge.seen:
        assert "false_alarm" not in finding.summary
        assert "failure" not in finding.summary.replace("failure_", "")
        assert "root" in finding.summary
