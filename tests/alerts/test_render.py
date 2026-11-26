"""Tests for alert rendering."""

from datetime import UTC, datetime

from rolda.alerts import Alert, slack_text, webhook_payload
from rolda.detection import Confidence
from rolda.incidents import Incident


def _alert(hypothesis: str = "span_error at root > tool: boom") -> Alert:
    incident = Incident(
        trace_id="t1",
        rule="span_error",
        span_id="s1",
        evidence="boom",
        confidence=Confidence.HIGH,
        signature="a|span_error|tool|boom",
        path=("root", "tool"),
        detected_at=datetime(2026, 11, 26, 10, tzinfo=UTC),
    )
    return Alert(incident=incident, hypothesis=hypothesis)


def test_webhook_payload_has_the_incident_and_the_hypothesis() -> None:
    payload = webhook_payload(_alert())

    assert payload == {
        "trace_id": "t1",
        "rule": "span_error",
        "span_id": "s1",
        "confidence": "high",
        "signature": "a|span_error|tool|boom",
        "path": ["root", "tool"],
        "hypothesis": "span_error at root > tool: boom",
        "detected_at": "2026-11-26T10:00:00+00:00",
    }


def test_slack_text_names_rule_and_hypothesis() -> None:
    text = slack_text(_alert())

    assert "span_error" in text
    assert "root &gt; tool" in text
    assert "t1" in text


def test_slack_text_neutralizes_mentions_and_links() -> None:
    hostile = "<!channel> <@U123> <http://evil.example|click> a & b"

    text = slack_text(_alert(hostile))

    assert "<!channel>" not in text
    assert "<@U123>" not in text
    assert "<http" not in text
    assert "&lt;!channel&gt;" in text
    assert "a &amp; b" in text


def test_long_hypothesis_is_truncated() -> None:
    long = "x" * 5000

    assert len(webhook_payload(_alert(long))["hypothesis"]) <= 500
    assert len(slack_text(_alert(long))) < 800
