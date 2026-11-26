# 0001. Languages: Python for the core, TypeScript for the UI

Status: accepted

## Context

Rolda needs a backend (OTLP ingestion, API, worker, rules, judge) and,
from v0.2, its own web UI.

## Decision

- Core (API, worker, detection, judge): Python >= 3.12.
- UI (v0.2 onwards): TypeScript.
- The MVP (v0.1) has no UI. Grafana is the temporary interface.

## Consequences

- CI tests Python 3.12 only. Python 3.11 is dropped.
- The UI talks to the core only through the FastAPI HTTP API.
- The UI lives in its own directory with its own toolchain, so Python
  checks stay unchanged.
