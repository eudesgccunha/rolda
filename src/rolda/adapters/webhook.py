"""HTTP alert adapters: generic webhook and Slack incoming webhook."""

import asyncio
import http.client
import json
from typing import Any
from urllib.parse import urlsplit

from rolda.alerts import (
    Alert,
    AlertDeliveryError,
    google_chat_text,
    slack_text,
    teams_card,
    webhook_payload,
)


def _validated(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        msg = "webhook URL must be http or https with a host"
        raise ValueError(msg)
    try:
        parts.port  # noqa: B018 - reading it validates the port
    except ValueError as exc:
        msg = "webhook URL has an invalid port"
        raise ValueError(msg) from exc
    return url


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> None:
    parts = urlsplit(url)
    connection_class = (
        http.client.HTTPSConnection
        if parts.scheme == "https"
        else http.client.HTTPConnection
    )
    target = parts.path or "/"
    if parts.query:
        target = f"{target}?{parts.query}"
    conn = connection_class(parts.hostname or "", parts.port, timeout=timeout)
    try:
        conn.request(
            "POST",
            target,
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        response.read()
        if not 200 <= response.status < 300:
            msg = f"webhook answered HTTP {response.status}"
            raise AlertDeliveryError(msg)
    except (OSError, http.client.HTTPException, ValueError) as exc:
        msg = f"webhook request failed: {type(exc).__name__}"
        raise AlertDeliveryError(msg) from exc
    finally:
        conn.close()


class _HttpAlerter:
    """Shared transport: validate the URL, POST a JSON body in a thread."""

    def __init__(self, url: str, timeout: float = 5.0) -> None:
        self._url = _validated(url)
        self._timeout = timeout

    def _body(self, alert: Alert) -> dict[str, Any]:
        raise NotImplementedError

    async def send(self, alert: Alert) -> None:
        """Deliver the alert."""
        await asyncio.to_thread(
            _post_json, self._url, self._body(alert), self._timeout
        )


class WebhookAlerter(_HttpAlerter):
    """POST the alert as JSON to a URL."""

    name = "webhook"

    def _body(self, alert: Alert) -> dict[str, Any]:
        return webhook_payload(alert)


class SlackAlerter(_HttpAlerter):
    """POST the alert to a Slack incoming webhook."""

    name = "slack"

    def _body(self, alert: Alert) -> dict[str, Any]:
        return {"text": slack_text(alert)}


class GoogleChatAlerter(_HttpAlerter):
    """POST the alert to a Google Chat incoming webhook."""

    name = "google_chat"

    def _body(self, alert: Alert) -> dict[str, Any]:
        return {"text": google_chat_text(alert)}


class TeamsAlerter(_HttpAlerter):
    """POST an Adaptive Card to a Teams Workflows webhook."""

    name = "teams"

    def _body(self, alert: Alert) -> dict[str, Any]:
        return teams_card(alert)
