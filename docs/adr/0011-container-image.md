# 0011. Container image and Compose services

## Status

Accepted.

## Context

The worker and the API ran only with `uv run`. Developers need one command
that starts the whole stack, without changing what `docker compose up`
does today.

## Decision

- One image (`deploy/docker/Dockerfile`) holds both processes. The Compose
  `command` picks the worker or the API.
- Two build stages: `uv sync --locked --no-dev` in the first, only the
  virtualenv and `src/` copied to the second. The final image has no `uv`,
  tests, docs or examples. The base image and the `uv` image are pinned by
  digest, as the rest of the stack is.
- The process runs as an unprivileged user (uid 10001, no login shell).
- `.dockerignore` keeps `.env*`, `.git`, `.claude` and tests out of the
  build context, so a secret cannot end up in a layer.
- `worker` and `api` are in the Compose profile `app`. `docker compose up`
  still starts only ClickHouse, the Collector and PostgreSQL. The full
  stack starts with `docker compose --profile app up -d --build`.
- Both services run with a read-only root filesystem, a `tmpfs` at `/tmp`,
  all capabilities dropped and `no-new-privileges`.
- The API listens on all interfaces inside the container, but the port is
  published only on `127.0.0.1:8000`.
- `ROLDA_API_TOKEN` is optional in the Compose file, because Compose
  interpolates services of inactive profiles too, and a required variable
  would break `docker compose up` for people who do not use the API. The
  API itself refuses to start without a valid token.

## Consequences

- The image is for development and self-hosting on one machine. It is not
  published to a registry, and there is no TLS.
- Without a token the `api` container exits and Compose restarts it in a
  loop. Its log says which variable is missing.
- `rolda:dev` is built locally, so it is the only image without a digest.
- Python dependencies are locked by `uv.lock`, but the base image digest
  must be bumped by hand for security updates.
