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
| Alerts (webhook, Slack, Google Chat, Teams) | Working, payloads verified against a real HTTP receiver; **not** rendered in real chat apps. Failed deliveries are retried per channel (outbox, M8a) |
| Worker resilience (checkpoint, leader lock, whole traces, migrations, probes, metrics) | M8a implemented and verified on Docker Compose: integration tests pass and a kill test lost nothing. Not run on Kubernetes or under load |
| Labels and eval export (JSONL) | Working |
| Judge adapter (Anthropic) and kappa measurement | Implemented and tested against a fake API; **never run against the real API**; **no kappa published** |
| HTTP API (bearer token) | Working, verified on the real stores |
| Container image and Compose services | Working, verified on a developer machine |
| Web UI | Not started (planned for v0.2) |

## How each claim was checked

- **Unit tests:** 311, run on every push by CI (Python 3.12).
- **Integration tests:** 16, against the Compose stack (ClickHouse,
  PostgreSQL, Collector). Run by hand with `uv run pytest -m integration`.
  CI does not run them. The last full run, after M8a (2026-11-27), passed all
  16, including migrations on both databases, the checkpoint, the leader lock,
  the alert outbox and reading spans by trace id.
- **Static checks:** `ruff` (format and lint), `mypy --strict`, `bandit`.
- **Kill test (2026-11-27):** a 300-session run with ground truth while the
  leader worker was killed three times. Result: 19 of 19 timeouts, 14 of 14
  rate limits, 10 of 10 loops and 5 of 5 token blowups found, 5 of 8 latency
  outliers found, 0 of 244 healthy sessions flagged and 0 duplicate incidents.
  The simulated agent injected the faults, so these numbers show recovery, not
  production quality.
- **Simulated agent:** `examples/support_agent` sends OpenTelemetry traces
  from a small agent whose **model is simulated** (no API key) and whose
  tools and control flow are real code. Four runs with ground truth
  (300 to 400 sessions each) were used to measure and tune the rules.

## What is not proven

0. **Kubernetes and long runs.** The worker survived a kill test on one
   developer machine (Docker Compose, two replicas): during a 300-session run
   the leader was killed three times. Windows stayed contiguous, no incident
   was lost or duplicated, and recall on errors, loops and token outliers was
   unchanged (see below). Stopping the leader without a restart moved the work
   to the standby in 29 seconds. This was **not** run on Kubernetes, for
   hours, under load, or with the databases failing.

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

- **Error text is stored.** A span's status message is kept in the
  incident evidence and appears in alerts and in the API. It is untrusted
  text from your agent and is **not redacted**: it can contain data. The
  eval export and the judge do not receive it. Only the agent, rule and
  operation of the signature leave the database.
- **Partial traces can still be judged.** The worker waits up to `lag`
  (10 minutes) for a trace's root span. A trace that runs longer than that
  can be judged early. Errors and loops only grow with more spans, but an
  outlier rule may score such a trace by a partial duration.
- **A restart can repeat work.** The cursor is saved after each window, so a
  restart resumes from it and an outage up to 24 hours is caught up. A longer
  outage skips the oldest part and logs it. A worker killed between saving
  and checkpointing repeats one window, which is safe because incidents are
  idempotent.
- **Alerts are at least once per channel.** A killed worker can send the same
  alert twice. A channel that never works is dropped after 5 attempts.
- **A history with no spread uses a 5% floor** (ADR 0015). That number is a
  judgment, not a measurement.

- One shared bearer token for the API. No users, roles or rate limiting.
  Put TLS in front before exposing it.
- The OTLP receiver has no authentication. The Compose file binds it to
  `127.0.0.1`.
- The in-memory adapters exist next to the real ones, for tests.
- No call ceiling for the judge, and no check that the judge model differs
  from the agent's model.
- Prompt and response content is not part of the data model. The judge and
  the evals see behavior only: spans, tools, status, tokens and durations.
- The worker is not wired to the judge. Judging is measured first.

## Scalability

Measured on one core: normalizing runs at about 117,000 spans per second and
a retained span takes about 442 bytes. CPU is not the limit.

Done in M8a: a checkpoint and a leader lock (so a second replica is a hot
standby, not a duplicate), whole-trace evaluation, versioned migrations, a
readiness probe, worker health and Prometheus metrics, and an alert outbox.

Still limits, planned for M8b and M8c:

- The worker loads the 7-day baseline as Python objects every hour. By the
  measurement above, 10 spans per second needs roughly 3 GB for the baseline
  alone and 100 spans per second roughly 27 GB (an estimate, and it ignores
  the raw rows held at the same time). The baseline should be computed inside
  ClickHouse instead.
- Only the leader works, so extra replicas add availability, not throughput.
  Scaling out needs a partition by trace id.
- Every database call opens its own connection, and the `agent` filter of the
  API has no index.
- The databases are single nodes, and the Collector queue is in memory, so a
  killed Collector pod loses its batch.
- There are no Kubernetes manifests or Helm chart yet, and no load test.

Fine for a small deployment (a few spans per second). Not ready for high
volume. The plan for the rest of M8 is in the project history: baseline in
ClickHouse, a connection pool, a load test, sharding, manifests and a chaos
test.

## What is needed to move forward

| To do | Requirement |
|---|---|
| Measure the judge (kappa) | An agent in real use, and about 30 incidents labeled by a human, plus an `ANTHROPIC_API_KEY` |
| Calibrate thresholds | Traces from a real agent over several days |
| Check alert rendering | A webhook URL for a test channel (a free Slack workspace is enough) |

## Repository hardening

- [x] Apache-2.0 license, code of conduct, security policy.
- [x] Repository public, `develop` merged into `main`.
- [x] `main` protected: pull request and `checks (3.12)` required, no force
  push or deletion, administrators included.
- [x] Private vulnerability reporting, secret scanning and push protection on.
- [x] Actions pinned by SHA (enforced), `zizmor` and `pip-audit` in CI,
  Dependabot with a 7 day cooldown, CodeQL, `CODEOWNERS`.
- [ ] Two-factor authentication with a passkey or hardware key, and narrow,
  short-lived tokens, on the maintainer's account. GitHub does not expose this
  to the project, so it is unverified here.

## Differences from the original plan

The plan is in [SPEC.md](SPEC.md).

- The judge adapter talks to the Anthropic API. The OpenAI-compatible and
  Bedrock strategies in the plan are not built.
- Google Chat and Teams were added next to the generic webhook and Slack.
- Two per-span rules were added: `span_latency_outlier` and
  `span_token_outlier`. Redundant outliers are dropped when a trace
  already has an error or a loop.
- Thresholds can be set per rule from the environment.
- M8 (worker resilience, scale, Kubernetes) was added after the plan.
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
| M8a Worker resilience (added) | Done, verified on Docker Compose |
| M8b Scale (baseline in ClickHouse, pool, load test) | Not started |
| M8c Kubernetes (sharding, manifests, chaos test) | Not started |
