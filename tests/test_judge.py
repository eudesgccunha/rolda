"""Tests for the judge port."""

import asyncio

from rolda.judge import DisabledJudge, Finding, Judge, Verdict


def test_disabled_judge_asks_for_human_review() -> None:
    judge: Judge = DisabledJudge()
    finding = Finding(
        trace_id="abc123",
        rule="tool_loop",
        evidence="search() called 5 times with the same arguments",
    )

    judgement = asyncio.run(judge.evaluate(finding))

    assert judgement.verdict is Verdict.UNCERTAIN
    assert "tool_loop" in judgement.reason
