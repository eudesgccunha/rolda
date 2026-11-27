"""Run the worker: ``python -m rolda.entrypoints``."""

import asyncio
import contextlib
import logging
import os
import signal
import sys
from collections.abc import Callable
from datetime import timedelta

from rolda.adapters.clickhouse import ClickHouseSpanSource
from rolda.adapters.postgres import (
    PostgresCheckpointStore,
    PostgresIncidentStore,
    PostgresLeadership,
)
from rolda.adapters.webhook import (
    GoogleChatAlerter,
    SlackAlerter,
    TeamsAlerter,
    WebhookAlerter,
)
from rolda.alerts import Alerter
from rolda.detection import default_rules
from rolda.entrypoints.settings import Settings, SettingsError, load_settings
from rolda.entrypoints.worker import (
    Worker,
    WorkerConfig,
    register_worker_metrics,
    serve,
)
from rolda.observability import Metrics
from rolda.observability.status_server import StatusServer


def main() -> None:
    """Wire the adapters and run the worker loop."""
    logging.basicConfig(level=logging.INFO)
    try:
        settings = load_settings(os.environ)
    except SettingsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    alerters: list[Alerter] = []
    channels: list[tuple[str | None, Callable[[str], Alerter]]] = [
        (settings.webhook_url, WebhookAlerter),
        (settings.slack_webhook_url, SlackAlerter),
        (settings.google_chat_webhook_url, GoogleChatAlerter),
        (settings.teams_webhook_url, TeamsAlerter),
    ]
    for url, alerter_class in channels:
        if url:
            alerters.append(alerter_class(url))
    incidents = PostgresIncidentStore(settings.postgres_dsn)
    metrics = Metrics()
    register_worker_metrics(metrics)
    worker = Worker(
        source=ClickHouseSpanSource(settings),
        store=incidents,
        outbox=incidents,
        rules=default_rules(settings.detection),
        config=WorkerConfig(),
        alerters=alerters,
        metrics=metrics,
    )
    asyncio.run(_serve(worker, settings, metrics))


async def _serve(worker: Worker, settings: Settings, metrics: Metrics) -> None:
    """Run until SIGTERM or SIGINT, then release the lock and return."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)

    async def sleep(seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), seconds)

    status = StatusServer(
        metrics,
        host=settings.status_host,
        port=settings.status_port,
        # A window that takes this long without the loop moving is stuck.
        max_age=max(5 * settings.interval, timedelta(minutes=5)),
    )
    try:
        await status.start()
    except OSError:
        logging.getLogger(__name__).warning(
            "status server could not listen on %s:%d; continuing without it",
            settings.status_host,
            settings.status_port,
        )
    try:
        await serve(
            worker,
            settings,
            sleep=sleep,
            checkpoints=PostgresCheckpointStore(settings.postgres_dsn),
            leadership=PostgresLeadership(settings.postgres_dsn),
            stop=stop,
            metrics=metrics,
        )
    finally:
        await status.stop()
