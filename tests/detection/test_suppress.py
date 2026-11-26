"""Tests for dropping redundant outlier findings."""

from rolda.detection import Finding, suppress_redundant


def _finding(rule: str) -> Finding:
    return Finding(trace_id="t1", rule=rule, span_id="s1", evidence="x")


def test_outliers_are_dropped_when_the_trace_has_a_loop() -> None:
    findings = [
        _finding("tool_loop"),
        _finding("latency_outlier"),
        _finding("token_outlier"),
    ]

    kept = suppress_redundant(findings)

    assert [f.rule for f in kept] == ["tool_loop"]


def test_outliers_are_dropped_when_the_trace_has_an_error() -> None:
    kept = suppress_redundant(
        [_finding("span_error"), _finding("span_latency_outlier")]
    )

    assert [f.rule for f in kept] == ["span_error"]


def test_outliers_stay_when_nothing_explains_them() -> None:
    findings = [_finding("latency_outlier"), _finding("token_outlier")]

    assert suppress_redundant(findings) == findings


def test_primary_findings_always_stay() -> None:
    findings = [_finding("span_error"), _finding("tool_loop")]

    assert suppress_redundant(findings) == findings


def test_unknown_rules_are_kept() -> None:
    findings = [_finding("tool_loop"), _finding("custom_rule")]

    assert suppress_redundant(findings) == findings
