"""Run the worker: ``python -m rolda.entrypoints``."""

import asyncio
import logging
import os
from collections.abc import Callable

from rolda.adapters.clickhouse import ClickHouseSpanSource
from rolda.adapters.postgres import PostgresIncidentStore
from rolda.adapters.webhook import (
    GoogleChatAlerter,
    SlackAlerter,
    TeamsAlerter,
    WebhookAlerter,
)
from rolda.alerts import Alerter
from rolda.detection import DetectionConfig, default_rules
from rolda.entrypoints.settings import load_settings
from rolda.entrypoints.worker import Worker, WorkerConfig, serve


def main() -> None:
    """Wire the adapters and run the worker loop."""
    logging.basicConfig(level=logging.INFO)
    settings = load_settings(os.environ)
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
    worker = Worker(
        source=ClickHouseSpanSource(settings),
        store=PostgresIncidentStore(settings.postgres_dsn),
        rules=default_rules(DetectionConfig()),
        config=WorkerConfig(),
        alerters=alerters,
    )
    asyncio.run(serve(worker, settings))


if __name__ == "__main__":
    main()
