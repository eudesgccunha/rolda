# 0014. Alert outbox

## Status

Accepted. It refines the delivery rule of [ADR 0006](0006-alerts-and-probable-cause.md).

## Context

ADR 0006 logged a failed alert and dropped it. A process killed between saving
an incident and sending its alert also lost it, and the incident was never
alerted again because it already existed. Restarts and rolling updates in an
orchestrator make that window real.

## Decision

- Saving a new incident also queues one delivery per configured channel, in
  the same PostgreSQL transaction (`alert_deliveries`, migration 005). The
  incident and its pending alerts exist together or not at all.
- After saving, the worker tries each channel and records the result. A
  channel that fails stays pending and is retried at the start of later
  windows, waiting `alert_backoff` times the number of failures (default
  30 s), up to `alert_max_attempts` (default 5). Then it is dropped and
  logged.
- Delivery is tracked per channel. A working channel is never sent the same
  alert again because another channel failed.
- A channel removed from the configuration has its pending deliveries drop
  after the same number of attempts.
- A retried alert rebuilds its hypothesis from the stored incident (path,
  rule and evidence), so it reads the same as the first one.
- Incidents that existed before migration 005 have no deliveries, so nothing
  is resent for them.

## Consequences

- The guarantee is at least once per channel. If the process dies after the
  channel accepted the request and before the result is recorded, that alert
  is sent again.
- A retry is only as prompt as the next window (the worker interval), not a
  separate timer.
- A permanently broken channel costs `alert_max_attempts` requests per
  incident and then stops.
