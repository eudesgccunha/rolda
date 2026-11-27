"""Helpers to call the API in tests."""

import http.client
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Reply:
    """What the API answered."""

    status: int
    headers: dict[str, str]
    text: str

    def json(self) -> Any:
        """Decode the body as JSON."""
        return json.loads(self.text)


class ApiClient:
    """Tiny HTTP client for the tests."""

    def __init__(self, port: int, token: str | None) -> None:
        self._port = port
        self._token = token

    def call(
        self,
        method: str,
        path: str,
        *,
        body: object | None = None,
        token: str | None = None,
        send_token: bool = True,
        headers: dict[str, str] | None = None,
    ) -> Reply:
        """Send one request. By default it carries the valid token."""
        sent = {"Content-Type": "application/json"}
        chosen = token if token is not None else self._token
        if send_token and chosen is not None and not headers:
            sent["Authorization"] = f"Bearer {chosen}"
        sent.update(headers or {})
        conn = http.client.HTTPConnection("127.0.0.1", self._port, timeout=10)
        try:
            conn.request(
                method,
                path,
                body=None if body is None else json.dumps(body),
                headers=sent,
            )
            response = conn.getresponse()
            return Reply(
                status=response.status,
                headers={k.lower(): v for k, v in response.getheaders()},
                text=response.read().decode("utf-8"),
            )
        finally:
            conn.close()
