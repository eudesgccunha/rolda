# 0018. Connection pool and an indexed agent column

## Status

Accepted.

## Context

Every PostgreSQL call opened its own connection: each incident saved, each
delivery marked, each API request. That costs a TCP and authentication round
trip per call, and a burst can exceed the server's connection limit.

The API filters incidents by agent with `split_part(signature, '|', 1)`, which
no index can serve, so each filtered page scanned every incident.

## Decision

- `psycopg_pool` (new dependency, approved) provides one `AsyncConnectionPool`
  per process, sized by `ROLDA_POSTGRES_POOL_SIZE` (default 5). The worker
  opens it at start and closes it on shutdown. The API opens and closes it in
  its startup and shutdown hook (`create_app(resources=[pool])`).
- The stores take an optional pool. Without one they open a connection per call
  as before, which is what the CLI and most tests use. `PostgresConnections`
  is the single place that decides.
- The leader lock keeps its own dedicated connection, because a session level
  advisory lock lives and dies with its connection.
- Migration 006 adds `incidents.agent` (filled from the signature for existing
  rows) and two indexes that match the listing order: one by agent, one
  global. The API filters on the column.

## Consequences

- Concurrent work now queues for at most `ROLDA_POSTGRES_POOL_SIZE`
  connections. Raise it if the logs show waiting.
- The agent is stored twice: in the signature and in the column. The store
  writes both from the same value, so they cannot differ.
- The readiness check still opens one connection per probe. That is on
  purpose: a probe that borrows from the pool could hide a pool that is full.
