# 0012. Versioned schema migrations

## Status

Accepted.

## Context

The SQL ran only through `docker-entrypoint-initdb.d`, which runs once, on an
empty volume. A deployment with data, or with a managed database, had no way
to receive a new table. Label support (migration 003) had to be applied by
hand.

## Decision

- The SQL files moved to `src/rolda/migrations/postgres` and
  `src/rolda/migrations/clickhouse`, named `NNN_name.sql`, so they ship in the
  package and in the container image. Compose mounts the same directories
  into `docker-entrypoint-initdb.d`, so a new volume still starts ready.
- `python -m rolda.entrypoints.migrate` applies what is missing, in order,
  and records each version with the SHA-256 of the file in a
  `schema_migrations` table in each database.
- Editing an applied file is refused (checksum mismatch): add a new
  migration instead. A version the database has but the code does not is
  only logged, so rolling the image back does not block.
- PostgreSQL: one transaction per file, and an advisory lock so two runners
  never overlap. ClickHouse: no transaction and no lock, because DDL is not
  transactional there.
- Every statement must be safe to run twice (`IF NOT EXISTS`). A test
  enforces it, because Compose runs the files too, before the runner has
  recorded anything.
- Compose has a one-shot `migrate` service in the `app` profile. The worker
  and the API wait for it to finish. In Kubernetes the same command runs as
  a Job.

## Consequences

- Existing deployments need nothing: the first run re-applies the old files
  harmlessly and records them.
- Destructive migrations (`DROP`) are not allowed by the tests and need a
  separate decision.
- A failed ClickHouse migration can leave a partly applied file. Because the
  statements are idempotent, running it again finishes the job.
