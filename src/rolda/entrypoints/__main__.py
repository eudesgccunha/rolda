"""Run the worker: ``python -m rolda.entrypoints``."""

import asyncio
import logging
import os

from rolda.adapters.clickhouse import ClickHouseSpanSource
from rolda.adapters.postgres import PostgresIncidentStore
from rolda.detection import DetectionConfig, default_rules
from rolda.entrypoints.settings import load_settings
from rolda.entrypoints.worker import Worker, WorkerConfig, serve


def main() -> None:
    """Wire the adapters and run the worker loop."""
    logging.basicConfig(level=logging.INFO)
    settings = load_settings(os.environ)
    worker = Worker(
        source=ClickHouseSpanSource(settings),
        store=PostgresIncidentStore(settings.postgres_dsn),
        rules=default_rules(DetectionConfig()),
        config=WorkerConfig(),
    )
    asyncio.run(serve(worker, settings))


if __name__ == "__main__":
    main()
