# 0016. Probes and metrics

## Status

Accepted.

## Context

An orchestrator needs to know whether a process is alive and whether it can
serve, and operators need to see how far behind the worker is. The API had
only `/health`, which touches no dependency, and the worker had nothing.

## Decision

- API: `GET /ready` (no token, like `/health`) runs a `SELECT 1` on PostgreSQL
  and ClickHouse with a 3 second timeout each. It answers 200, or 503 with the
  names of the failed dependencies. The reason is logged, never returned,
  because it can contain connection details. `/health` stays a pure liveness
  check.
- Worker: a small asyncio HTTP server (`ROLDA_STATUS_HOST`, default
  `127.0.0.1`, and `ROLDA_STATUS_PORT`, default 9100) answers `GET /healthz`
  and `GET /metrics` and nothing else. It has a read timeout and size limits.
  If the port is taken the worker logs a warning and keeps working.
- `/healthz` is 200 while the main loop ran in the last
  `max(5 * interval, 5 minutes)`. A standby worker iterates too, so it is
  alive. A worker blocked inside one window for longer than that is reported
  stalled, which is what a liveness probe should restart.
- `/metrics` uses the Prometheus text format, written by hand in
  `rolda.observability` (no new dependency): windows by result, new incidents,
  alert attempts by channel and result, leader flag, cursor timestamp and lag.
- The worker has no readiness probe. It serves nobody, and the lag gauge is
  what an alert should watch.

## Consequences

- The metrics endpoint is not authenticated. It carries counts only, and it is
  bound to loopback by default. Open it to the cluster network on purpose and
  restrict it there.
- The API has no `/metrics` yet.
- Metrics live in the process: a restart resets the counters, which
  Prometheus handles as a counter reset.
