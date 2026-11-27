# 0013. Worker checkpoint and leader lock

## Status

Accepted.

## Context

The worker kept the end of its last window in memory. After a restart it
resumed at "now minus the window", so an outage longer than the window left
those traces unanalyzed, silently. Two worker replicas repeated the same work.
Both matter once the worker runs under an orchestrator that restarts and
replaces pods.

## Decision

- A `CheckpointStore` port saves the worker cursor. PostgreSQL keeps it in
  `worker_state` (migration 004), one row per worker name. The cursor moves
  only after a window ran and the checkpoint was written, so a crash
  re-reads the same window. Incidents are idempotent, so that is safe.
- After an outage the worker resumes from the cursor. It never goes back more
  than `ROLDA_MAX_CATCHUP_SECONDS` (default 24 h) and logs what it skips. It
  catches up in chunks of at most `ROLDA_CHUNK_SECONDS` (default 1 h), with no
  sleep between chunks, so a long gap does not load one huge window.
- A `Leadership` port lets one worker at a time work. PostgreSQL implements it
  with `pg_try_advisory_lock` on a connection that stays open. The lock
  disappears with the connection, so a dead or partitioned worker never keeps
  it. A standby replica checks again every interval and takes over, resuming
  from the shared checkpoint.
- The worker stops on SIGTERM or SIGINT after the current iteration, and
  releases the lock.
- A failed window, including a failed checkpoint write, is logged and retried
  from the same start.

## Consequences

- Replicas give availability, not throughput: only the leader works.
  Sharding by trace id is a later step.
- The guarantee is at least once. A worker killed after saving incidents and
  before writing the checkpoint repeats that window.
- An alert can still be lost if the process dies between saving an incident
  and sending it. The alert outbox closes that gap.
- Time moves forward only: the cursor is wall-clock time, so a clock that
  jumps backwards on the worker host reprocesses a window. That is harmless.
