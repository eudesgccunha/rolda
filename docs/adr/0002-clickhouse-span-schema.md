# 0002. ClickHouse span schema owned by Rolda

Status: accepted

## Context

The OpenTelemetry Collector `clickhouse` exporter can create its own
tables. Its schema changes between versions, and Rolda needs control of
retention and indexes.

## Decision

- The schema lives in `src/rolda/migrations/clickhouse/001_spans.sql` and is applied
  by the ClickHouse image on first start.
- The exporter runs with `create_schema: false`.
- Columns match the exporter v0.166.0 insert statement. The Collector and
  ClickHouse images are pinned by version and digest.
- Retention is a `TTL` clause in the SQL (30 days by default).

## Consequences

- Upgrading the Collector needs a check of the exporter insert columns.
- Schema changes ship as new numbered SQL files. The init directory runs
  only on an empty data volume, so existing volumes need a manual
  migration until a migration tool exists.
