"""A real Collector refuses OTLP writes without the bearer token.

Needs Docker and the pinned Collector image (it is pulled when missing). It
does not touch the Compose stack: it starts a throwaway container with the
same authentication stanza as the shipped configs and a ``debug`` exporter.
"""

import http.client
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

IMAGE = (
    "otel/opentelemetry-collector-contrib:0.166.0@sha256:"
    "3e18fe04181de50bdd72e23ad4a4d6214b54351e63d496f1c58127cc4541ad7f"
)
TOKEN = "integration-otlp-token-0123456789"  # noqa: S105 - fake token
CONFIG = """
extensions:
  bearertokenauth:
    scheme: Bearer
    token: ${env:ROLDA_OTLP_TOKEN}
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
        auth:
          authenticator: bearertokenauth
exporters:
  debug: {}
service:
  extensions: [bearertokenauth]
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [debug]
"""


def _post(port: int, authorization: str | None) -> int:
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(
            "POST", "/v1/traces", body='{"resourceSpans":[]}', headers=headers
        )
        response = conn.getresponse()
        response.read()
        return response.status
    finally:
        conn.close()


DOCKER = shutil.which("docker") or "docker"


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs Docker")
def test_writes_need_the_bearer_token(tmp_path: Path) -> None:
    config = tmp_path / "otelcol.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    name = f"rolda-otlp-auth-{uuid.uuid4().hex[:8]}"
    subprocess.run(  # noqa: S603 - fixed arguments, no user input
        [
            DOCKER,
            "run",
            "-d",
            "--name",
            name,
            "-e",
            f"ROLDA_OTLP_TOKEN={TOKEN}",
            "-p",
            "127.0.0.1::4318",
            "-v",
            f"{config}:/etc/otelcol.yaml:ro",
            IMAGE,
            "--config=/etc/otelcol.yaml",
        ],
        check=True,
        capture_output=True,
    )
    try:
        port = int(
            subprocess.run(  # noqa: S603 - fixed arguments
                [DOCKER, "port", name, "4318/tcp"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.split(":")[-1]
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                _post(port, None)
                break
            except OSError:
                time.sleep(0.5)

        assert _post(port, None) == 401
        assert _post(port, "Bearer not-the-token") == 401
        assert _post(port, f"Basic {TOKEN}") == 401
        assert _post(port, f"Bearer {TOKEN}") == 200
    finally:
        subprocess.run(  # noqa: S603 - fixed arguments
            [DOCKER, "rm", "-f", name], check=False, capture_output=True
        )
