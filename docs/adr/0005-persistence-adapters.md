# 0005. Persistence adapters and the worker process

Status: accepted

## Context

M3 had only in-memory adapters, so the worker could not run against the
Compose stack. SPEC.md plans ClickHouse for spans and PostgreSQL for state.

## Decision

- Adapters live in `src/rolda/adapters/`, outside the domain folders, and
  are wired only in `rolda.entrypoints.__main__`.
- `ClickHouseSpanSource` uses `clickhouse-connect` (HTTP) with
  server-side bound parameters, run in a thread to keep the port async.
  Rows that fail normalization are counted and skipped.
- `PostgresIncidentStore` uses `psycopg` 3 and
  `INSERT ... ON CONFLICT (trace_id, rule) DO NOTHING`.
- Configuration comes from environment variables only (`Settings`).
  Credentials are URL-quoted when they build the PostgreSQL DSN.
- `serve` runs contiguous windows. `python -m rolda.entrypoints` starts it.

## Consequences

- Each window reads the 7-day baseline again. This costs more as data
  grows, so cache or pre-aggregate it once volumes are measured.
- `Worker` opens one PostgreSQL connection per saved incident. Use a pool
  if incident volume grows.
- No Dockerfile yet: the worker runs with `uv run python -m
  rolda.entrypoints`.
