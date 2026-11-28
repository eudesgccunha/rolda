# 0019. Sharding the worker by trace id

## Status

Accepted.

## Context

Only the leader worked, so extra replicas added availability but no
throughput. At high volume one worker is the limit (ADR 0016 and the M8
measurements).

## Decision

- Traces are split by `crc32(trace_id) % ROLDA_SHARD_COUNT`. Worker `i` handles
  the traces whose remainder is `ROLDA_SHARD_INDEX`. CRC32 is the same in
  Python and in ClickHouse, so the database does the filtering and a worker
  never reads traces that are not its own.
- `ROLDA_SHARD_INDEX` can be `auto`: the number at the end of `HOSTNAME`, which
  is the ordinal of a StatefulSet pod. Settings are checked at start, and a
  bad shard stops the worker.
- Each shard has its own checkpoint and leader lock, named `worker-<index>`
  (one shard keeps the old name `worker`). A shard can have standby replicas
  that wait for its lock.
- The filter applies to the window and to the baseline slices, so each shard
  learns what is normal from its own share of the traces. A trace is read by
  its owner only. Reading a trace by id (`spans_for_traces`) is not filtered.

## Consequences

- Changing the shard count moves traces between workers. Incidents are keyed
  by trace and rule, so nothing is duplicated, but the checkpoints of the old
  shards no longer match. Start the new set from a clean checkpoint or accept
  that some windows are read again.
- A shard sees about `1/N` of the traces. An agent with little traffic can fall
  below `ROLDA_MIN_SAMPLES` on a shard and get no outlier rules there. Lower the
  shard count, or `ROLDA_MIN_SAMPLES`.
- The split is uniform for random trace ids. It is not balanced by agent.
