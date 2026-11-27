# 0004. Idempotent incidents and window lag

Status: accepted

## Context

The MVP has no queue. The worker reads spans by time window, and spans can
arrive late. Reprocessing a window must not duplicate incidents (M3
acceptance criterion).

## Decision

- An incident is unique per `(trace_id, rule)`. `IncidentStore.save`
  returns whether the incident was new.
- Each window run also reads `lag` (default 2 minutes) before its start,
  so late spans are evaluated in the next run.
- Outlier rules use a per-agent baseline from the previous 7 days, read
  through the same `SpanSource` port. They need 30 samples and skip a MAD
  of zero.
- `span_error` points at the earliest error span with no failing child,
  not at the root that only propagates the error.
- Only in-memory adapters exist in M3. ClickHouse and PostgreSQL adapters
  need their own milestone.

## Consequences

- A late error span in a trace that already has a `span_error` incident is
  not recorded again.
- The detection `Finding` carries a span id and confidence. The judge
  port's own `Finding` should adopt it when M6 starts.
