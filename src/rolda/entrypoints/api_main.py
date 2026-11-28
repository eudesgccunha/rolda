"""Run the API: ``python -m rolda.entrypoints.api_main``."""

import logging
import os
import sys

import uvicorn
from psycopg_pool import AsyncConnectionPool

from rolda.adapters.clickhouse import ClickHouseSpanSource
from rolda.adapters.health import clickhouse_check, postgres_check
from rolda.adapters.postgres import PostgresIncidentStore, PostgresLabelStore
from rolda.entrypoints.api import create_app
from rolda.entrypoints.settings import (
    SettingsError,
    load_api_settings,
    load_settings,
)


def main() -> None:
    """Wire the adapters and serve the API."""
    logging.basicConfig(level=logging.INFO)
    try:
        settings = load_settings(os.environ)
        api = load_api_settings(os.environ)
    except SettingsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    pool = AsyncConnectionPool(
        settings.postgres_dsn,
        min_size=1,
        max_size=settings.postgres_pool_size,
        open=False,
    )
    app = create_app(
        incidents=PostgresIncidentStore(settings.postgres_dsn, pool),
        labels=PostgresLabelStore(settings.postgres_dsn, pool),
        spans=ClickHouseSpanSource(settings),
        token=api.token,
        docs=api.docs,
        resources=[pool],
        readiness={
            "postgres": postgres_check(settings.postgres_dsn),
            "clickhouse": clickhouse_check(settings),
        },
    )
    uvicorn.run(app, host=api.host, port=api.port, log_level="info")


if __name__ == "__main__":
    main()
