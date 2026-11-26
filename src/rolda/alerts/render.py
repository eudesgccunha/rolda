"""Alert rendering for each channel.

Hypotheses and evidence come from trace content, which is untrusted.
"""

from typing import Any

from rolda.alerts.model import Alert

_MAX_HYPOTHESIS = 500


def _short(text: str) -> str:
    return text[:_MAX_HYPOTHESIS]


def _slack_escape(text: str) -> str:
    # Slack treats <...> as mentions and links, so neutralize them.
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def webhook_payload(alert: Alert) -> dict[str, Any]:
    """Return the JSON body sent to a generic webhook."""
    incident = alert.incident
    return {
        "trace_id": incident.trace_id,
        "rule": incident.rule,
        "span_id": incident.span_id,
        "confidence": incident.confidence.value,
        "signature": incident.signature,
        "path": list(incident.path),
        "hypothesis": _short(alert.hypothesis),
        "detected_at": incident.detected_at.isoformat(),
    }


def slack_text(alert: Alert) -> str:
    """Return the Slack message text, escaped."""
    incident = alert.incident
    head = _slack_escape(
        f"Rolda: {incident.rule} ({incident.confidence.value}) "
        f"trace {incident.trace_id}"
    )
    return f"*{head}*\n{_slack_escape(_short(alert.hypothesis))}"


def google_chat_text(alert: Alert) -> str:
    """Return the Google Chat message text.

    Chat has no documented escape for ``<users/all>`` style mentions, so
    angle brackets become look-alike characters.
    """
    incident = alert.incident
    head = (
        f"Rolda: {incident.rule} ({incident.confidence.value}) "
        f"trace {incident.trace_id}"
    )
    return _chat_safe(f"*{head}*\n{_short(alert.hypothesis)}")


def _chat_safe(text: str) -> str:
    return text.replace("<", "\u2039").replace(">", "\u203a")


def _teams_safe(text: str) -> str:
    # Adaptive Card text renders markdown: break link and code syntax.
    return text.replace("[", "(").replace("]", ")").replace("`", "'")


def teams_card(alert: Alert) -> dict[str, Any]:
    """Return a Teams Workflows webhook body with an Adaptive Card."""
    incident = alert.incident
    title = (
        f"Rolda: {incident.rule} ({incident.confidence.value}) "
        f"trace {incident.trace_id}"
    )
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": (
                        "http://adaptivecards.io/schemas/adaptive-card.json"
                    ),
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": _teams_safe(title),
                            "weight": "Bolder",
                            "wrap": True,
                        },
                        {
                            "type": "TextBlock",
                            "text": _teams_safe(_short(alert.hypothesis)),
                            "wrap": True,
                        },
                    ],
                },
            }
        ],
    }
