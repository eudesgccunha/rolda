# 0010. HTTP API

## Status

Accepted.

## Context

A future UI and integrations need to read incidents and record labels. The
SPEC requires authentication before the API is exposed on a network.

## Decision

- FastAPI served by uvicorn (new dependencies, approved).
  `python -m rolda.entrypoints.api_main` starts it.
- Routes: `GET /health` (open), `GET /incidents` (filters `rule`, `agent`,
  `limit` up to 200, opaque `cursor`), `GET /incidents/{trace_id}`,
  `GET /incidents/{trace_id}/trace`, `PUT /incidents/{trace_id}/{rule}/label`
  and `GET /evals/export`. Everything but `/health` needs
  `Authorization: Bearer <ROLDA_API_TOKEN>`.
- One shared token for the MVP, compared in constant time. The token must
  have at least 16 characters and the API does not start without it. Users
  and roles are out of scope.
- The API binds to `127.0.0.1` by default (`ROLDA_API_HOST`,
  `ROLDA_API_PORT`). The OpenAPI docs are off unless `ROLDA_API_DOCS` is
  true. No CORS is configured.
- The only write is a human label. The body rejects unknown fields and
  limits the lengths of `reason` (500) and `labeler` (64).
- Trace content is untrusted. It is returned only as JSON fields, never
  as HTML. The trace route lists spans of traces that have an incident,
  with behavior only: no prompt, response or tool arguments.
- Paging uses the cursor `(detected_at, trace_id, rule)`, newest first,
  so equal timestamps neither skip nor repeat an incident. Filters are
  bound parameters.
- The read side is two new port methods: `IncidentStore.list` and
  `for_trace`, plus `LabelStore.for_trace`.
- Tests run a real uvicorn server on a free local port and use
  `http.client`, so no test-only HTTP dependency was added.

## Consequences

- A single shared token cannot tell users apart. `labeler` is whatever the
  caller sends. Do not expose the API without TLS in front of it.
- Each request opens its own database connection. Pool them when the
  traffic needs it.
- There is no rate limiting.
- The API and the worker are separate processes that share the stores.
