# Project status

Last updated: 2026-11-27. Version: 0.1 (MVP), pre-release.

Rolda's MVP is built and tested end to end on a local stack. It has **not**
yet been validated on traffic from a real agent. This page says what is
proven, what is not, and what is needed to close the gap.

## Summary

| Area | State |
|---|---|
| Ingestion (OTLP → Collector → ClickHouse) | Working, verified on the Compose stack |
| Normalization and domain model | Working |
| Detection (6 rules) | Working, thresholds calibrated on **simulated** data only |
| Incidents, probable cause, idempotent storage | Working, verified on PostgreSQL |
| Alerts (webhook, Slack, Google Chat, Teams) | Working, payloads verified against a real HTTP receiver; **not** rendered in real chat apps |
| Labels and eval export (JSONL) | Working |
| Judge adapter (Anthropic) and kappa measurement | Implemented and tested against a fake API; **never run against the real API**; **no kappa published** |
| HTTP API (bearer token) | Working, verified on the real stores |
| Container image and Compose services | Working, verified on a developer machine |
| Web UI | Not started (planned for v0.2) |

## How each claim was checked

- **Unit tests:** 228, run on every push by CI (Python 3.12).
- **Integration tests:** 10, against the Compose stack (ClickHouse,
  PostgreSQL, Collector). Run by hand with `uv run pytest -m integration`.
  CI does not run them.
- **Static checks:** `ruff` (format and lint), `mypy --strict`, `bandit`.
- **Simulated agent:** `examples/support_agent` sends OpenTelemetry traces
  from a small agent whose **model is simulated** (no API key) and whose
  tools and control flow are real code. Four runs with ground truth
  (300 to 400 sessions each) were used to measure and tune the rules.

## What is not proven

1. **Real agent traffic.** Every trace so far comes from fixtures or the
   simulated agent. Thresholds, false-alarm rates and recall on real
   agents are unknown.
2. **Judge quality.** Cohen's kappa against human labels has never been
   measured. The judge has never made a real API call. Until it has, do
   not let it decide anything.
3. **Alert rendering.** The Slack, Google Chat and Teams payloads were
   checked as JSON received over HTTP, from the worker container. They
   have not been posted to a real channel.
4. **Detection numbers.** On simulated data the rules found all injected
   errors and loops, and 70 to 90% of injected latency and token
   outliers, with at most 1 false alarm in 300 healthy sessions
   ([ADR 0009](adr/0009-redundant-outliers-and-span-latency.md)). The
   faults were built to resemble what the rules look for, so these numbers
   show direction, not production performance.
5. **Scale.** No load test. Each API request opens its own database
   connection, and the worker reads whole time windows.

## Known limitations

- One shared bearer token for the API. No users, roles or rate limiting.
  Put TLS in front before exposing it.
- The OTLP receiver has no authentication. The Compose file binds it to
  `127.0.0.1`.
- Alert delivery is not retried; a failure is logged and dropped
  ([ADR 0006](adr/0006-alerts-and-probable-cause.md)).
- The in-memory adapters exist next to the real ones, for tests.
- No call ceiling for the judge, and no check that the judge model differs
  from the agent's model.
- Prompt and response content is not part of the data model. The judge and
  the evals see behavior only: spans, tools, status, tokens and durations.
- The worker is not wired to the judge. Judging is measured first.

## What is needed to move forward

| To do | Requirement |
|---|---|
| Measure the judge (kappa) | An agent in real use, and about 30 incidents labeled by a human, plus an `ANTHROPIC_API_KEY` |
| Calibrate thresholds | Traces from a real agent over several days |
| Check alert rendering | A webhook URL for a test channel (a free Slack workspace is enough) |
| Make the repository public | A license file (see below) and a decision to publish |

## Before making the repository public

- [ ] Choose a license and add `LICENSE`. The original plan suggests
  Apache-2.0 because it includes a patent grant. Until a license exists,
  nobody can legally reuse the code.
- [ ] Set the license in `pyproject.toml` and the README.
- [ ] Enable private vulnerability reporting on GitHub (see
  [SECURITY.md](../SECURITY.md) and [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md),
  which both point at it). GitHub offers it only on public repositories or
  paid plans, so do it the moment the repository goes public.
- [ ] Protect `main` (require a pull request and the `checks` status check,
  block force pushes and deletion). GitHub offers it only on public
  repositories or paid plans.
- [x] Code of conduct added (Contributor Covenant 2.1).
- [x] `develop` merged into `main`.

## Differences from the original plan

The plan is in [SPEC.md](SPEC.md).

- The judge adapter talks to the Anthropic API. The OpenAI-compatible and
  Bedrock strategies in the plan are not built.
- Google Chat and Teams were added next to the generic webhook and Slack.
- Two per-span rules were added: `span_latency_outlier` and
  `span_token_outlier`. Redundant outliers are dropped when a trace
  already has an error or a loop.
- Thresholds can be set per rule from the environment.
- An HTTP API and a container image were built, which the plan placed
  after the MVP milestones.
- The judge's call ceiling and the model-family preference from the plan
  are not enforced.

## Milestones

| Milestone | State |
|---|---|
| M0 Repository and CI | Done |
| M1 Compose with Collector and ClickHouse | Done |
| M2 Domain model and normalization | Done |
| M3 Rules and worker | Done |
| M4 Incidents, probable cause and alerts | Done |
| M5 Labels and eval export | Done |
| M6 Judge adapter | Adapter and kappa tooling done; **kappa not measured** |
| M7 HTTP API (added) | Done |
