"""Run the API: ``python -m rolda.entrypoints.api_main``."""

import logging
import os

import uvicorn

from rolda.adapters.clickhouse import ClickHouseSpanSource
from rolda.adapters.postgres import PostgresIncidentStore, PostgresLabelStore
from rolda.entrypoints.api import create_app
from rolda.entrypoints.settings import load_api_settings, load_settings


def main() -> None:
    """Wire the adapters and serve the API."""
    logging.basicConfig(level=logging.INFO)
    settings = load_settings(os.environ)
    api = load_api_settings(os.environ)
    app = create_app(
        incidents=PostgresIncidentStore(settings.postgres_dsn),
        labels=PostgresLabelStore(settings.postgres_dsn),
        spans=ClickHouseSpanSource(settings),
        token=api.token,
        docs=api.docs,
    )
    uvicorn.run(app, host=api.host, port=api.port, log_level="info")


if __name__ == "__main__":
    main()
