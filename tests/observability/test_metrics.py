"""Tests for the metrics registry and the status server."""

import asyncio
import http.client
from datetime import UTC, datetime, timedelta

from rolda.observability import Metrics
from rolda.observability.status_server import StatusServer


def test_a_counter_renders_in_prometheus_text_format() -> None:
    metrics = Metrics()
    metrics.describe("rolda_things_total", "counter", "Things that happened.")

    metrics.inc("rolda_things_total")
    metrics.inc("rolda_things_total", value=2)

    text = metrics.render()
    assert "# HELP rolda_things_total Things that happened." in text
    assert "# TYPE rolda_things_total counter" in text
    assert "rolda_things_total 3\n" in text


def test_labels_are_rendered_and_escaped() -> None:
    metrics = Metrics()
    metrics.describe("rolda_x_total", "counter", "X.")

    metrics.inc("rolda_x_total", {"channel": 'a"b\\c\nd'})

    assert 'rolda_x_total{channel="a\\"b\\\\c\\nd"} 1' in metrics.render()


def test_a_gauge_keeps_the_last_value() -> None:
    metrics = Metrics()
    metrics.describe("rolda_g", "gauge", "G.")

    metrics.set("rolda_g", 5)
    metrics.set("rolda_g", 7.5)

    assert "rolda_g 7.5\n" in metrics.render()


def test_series_with_different_labels_are_separate() -> None:
    metrics = Metrics()
    metrics.describe("rolda_w_total", "counter", "W.")

    metrics.inc("rolda_w_total", {"result": "ok"})
    metrics.inc("rolda_w_total", {"result": "error"})
    metrics.inc("rolda_w_total", {"result": "ok"})

    text = metrics.render()
    assert 'rolda_w_total{result="ok"} 2' in text
    assert 'rolda_w_total{result="error"} 1' in text


def _get(port: int, path: str, method: str = "GET") -> tuple[int, str, str]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, path)
        response = conn.getresponse()
        return (
            response.status,
            response.getheader("Content-Type") or "",
            response.read().decode(),
        )
    finally:
        conn.close()


NOW = datetime(2026, 11, 26, 10, 0, tzinfo=UTC)


def test_metrics_and_health_are_served() -> None:
    metrics = Metrics()
    metrics.describe("rolda_up", "gauge", "Up.")
    metrics.set("rolda_up", 1)
    metrics.touch(NOW)
    results: dict[str, tuple[int, str, str]] = {}

    async def run() -> None:
        server = StatusServer(
            metrics,
            host="127.0.0.1",
            port=0,
            max_age=timedelta(seconds=60),
            clock=lambda: NOW + timedelta(seconds=10),
        )
        await server.start()
        try:
            for path in ("/metrics", "/healthz", "/nope"):
                results[path] = await asyncio.to_thread(
                    _get, server.port, path
                )
            results["POST"] = await asyncio.to_thread(
                _get, server.port, "/metrics", "POST"
            )
        finally:
            await server.stop()

    asyncio.run(run())

    status, content_type, body = results["/metrics"]
    assert status == 200
    assert content_type.startswith("text/plain")
    assert "rolda_up 1" in body
    assert results["/healthz"][0] == 200
    assert results["/nope"][0] == 404
    assert results["POST"][0] == 405


def test_health_fails_when_the_loop_stopped_iterating() -> None:
    metrics = Metrics()
    metrics.touch(NOW)
    answer: list[int] = []

    async def run() -> None:
        server = StatusServer(
            metrics,
            host="127.0.0.1",
            port=0,
            max_age=timedelta(seconds=60),
            clock=lambda: NOW + timedelta(seconds=120),
        )
        await server.start()
        try:
            status, _, _ = await asyncio.to_thread(
                _get, server.port, "/healthz"
            )
            answer.append(status)
        finally:
            await server.stop()

    asyncio.run(run())

    assert answer == [503]
