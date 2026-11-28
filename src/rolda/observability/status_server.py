"""A minimal HTTP server for ``/metrics`` and ``/healthz``.

It answers two GET paths and nothing else, with a short read timeout and
small size limits, so it can run next to the worker without a web framework.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from rolda.observability import Metrics

logger = logging.getLogger(__name__)

_MAX_LINE = 1024
_MAX_HEADERS = 50
_READ_TIMEOUT = 5.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


class StatusServer:
    """Serve the metrics and a liveness check for one process."""

    def __init__(
        self,
        metrics: Metrics,
        *,
        host: str,
        port: int,
        max_age: timedelta,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._metrics = metrics
        self._host = host
        self._port = port
        self._max_age = max_age
        self._clock = clock
        self._server: asyncio.Server | None = None

    @property
    def port(self) -> int:
        """The port the server listens on (useful when it was 0)."""
        if self._server is None or not self._server.sockets:
            msg = "the status server is not running"
            raise RuntimeError(msg)
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        """Start listening."""
        self._server = await asyncio.start_server(
            self._handle, self._host, self._port
        )

    async def stop(self) -> None:
        """Stop listening."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def _healthy(self) -> bool:
        last = self._metrics.last_iteration
        return last is not None and self._clock() - last <= self._max_age

    async def _read_request(
        self, reader: asyncio.StreamReader
    ) -> tuple[str, str] | None:
        line = await reader.readline()
        if not line or len(line) > _MAX_LINE:
            return None
        parts = line.decode("latin-1").split()
        if len(parts) != 3 or not parts[2].startswith("HTTP/"):
            return None
        for _ in range(_MAX_HEADERS):
            header = await reader.readline()
            if header in (b"\r\n", b"\n", b""):
                return parts[0], parts[1]
        return None

    def _answer(self, method: str, path: str) -> tuple[int, str, str]:
        if method != "GET":
            return 405, "text/plain", "method not allowed\n"
        route = path.split("?", 1)[0]
        if route == "/metrics":
            return 200, "text/plain; version=0.0.4", self._metrics.render()
        if route == "/healthz":
            if self._healthy():
                return 200, "text/plain", "ok\n"
            return 503, "text/plain", "stalled\n"
        return 404, "text/plain", "not found\n"

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request = await asyncio.wait_for(
                self._read_request(reader), _READ_TIMEOUT
            )
            if request is None:
                status, kind, body = 400, "text/plain", "bad request\n"
            else:
                status, kind, body = self._answer(*request)
            payload = body.encode()
            writer.write(
                f"HTTP/1.1 {status} X\r\nContent-Type: {kind}\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Connection: close\r\n\r\n".encode()
                + payload
            )
            await writer.drain()
        except (TimeoutError, ConnectionError):
            logger.debug("status request dropped")
        finally:
            writer.close()
