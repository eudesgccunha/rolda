"""Tests for the webhook and Slack adapters, against a real local server."""

import asyncio
import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from rolda.adapters.webhook import (
    GoogleChatAlerter,
    SlackAlerter,
    TeamsAlerter,
    WebhookAlerter,
)
from rolda.alerts import Alert, AlertDeliveryError
from rolda.detection import Confidence
from rolda.incidents import Incident


class _Receiver(BaseHTTPRequestHandler):
    status = 200
    received: list[dict[str, Any]] = []  # noqa: RUF012 - shared test state

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        type(self).received.append(
            {
                "http_path": self.path,
                "type": self.headers["Content-Type"],
                **body,
            }
        )
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Silence the default request log."""


@pytest.fixture
def server() -> Iterator[str]:
    _Receiver.received = []
    _Receiver.status = 200
    httpd = HTTPServer(("127.0.0.1", 0), _Receiver)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/hook"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _alert() -> Alert:
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
    return Alert(incident=incident, hypothesis="span_error at root > tool")


def test_webhook_receives_the_alert_as_json(server: str) -> None:
    asyncio.run(WebhookAlerter(server).send(_alert()))

    [received] = _Receiver.received
    assert received["http_path"] == "/hook"
    assert received["type"] == "application/json"
    assert received["trace_id"] == "t1"
    assert received["rule"] == "span_error"
    assert received["path"] == ["root", "tool"]


def test_slack_receives_text(server: str) -> None:
    asyncio.run(SlackAlerter(server).send(_alert()))

    [received] = _Receiver.received
    assert "span_error" in received["text"]


def test_google_chat_receives_text(server: str) -> None:
    asyncio.run(GoogleChatAlerter(server).send(_alert()))

    [received] = _Receiver.received
    assert "span_error" in received["text"]


def test_teams_receives_an_adaptive_card(server: str) -> None:
    asyncio.run(TeamsAlerter(server).send(_alert()))

    [received] = _Receiver.received
    assert received["type"] == "message"
    content = received["attachments"][0]["content"]
    assert content["type"] == "AdaptiveCard"


def test_http_error_status_raises_delivery_error(server: str) -> None:
    _Receiver.status = 500

    with pytest.raises(AlertDeliveryError, match="500"):
        asyncio.run(WebhookAlerter(server).send(_alert()))


def test_unreachable_server_raises_delivery_error() -> None:
    alerter = WebhookAlerter("http://127.0.0.1:9/hook", timeout=1.0)

    with pytest.raises(AlertDeliveryError):
        asyncio.run(alerter.send(_alert()))


@pytest.mark.parametrize(
    "url", ["ftp://example.com/x", "file:///etc/passwd", "http:///nohost"]
)
def test_only_http_urls_with_a_host_are_accepted(url: str) -> None:
    with pytest.raises(ValueError, match="webhook URL"):
        WebhookAlerter(url)


def test_a_bad_port_is_rejected_when_the_alerter_is_built() -> None:
    with pytest.raises(ValueError, match="port"):
        WebhookAlerter("http://hooks.example:80a/x")


def test_a_non_ascii_path_becomes_a_delivery_error(server: str) -> None:
    with pytest.raises(AlertDeliveryError):
        asyncio.run(WebhookAlerter(server + "/caf\u00e9").send(_alert()))
