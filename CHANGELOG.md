# Changelog

All notable changes are listed here. The project follows
[Semantic Versioning](https://semver.org) and
[PEP 440](https://peps.python.org/pep-0440/) for pre-releases.

## 0.1.0rc1 (pre-release)

The MVP is built and tested, but it is **not yet validated on a real agent**.
Read [docs/STATUS.md](docs/STATUS.md) for what is proven and what is not
before relying on it. In particular, the judge has never been measured against
human labels, so no kappa is published, which the plan asks for before 0.1.0.

### Added

- OTLP ingestion through the OpenTelemetry Collector into ClickHouse, and a
  normalization boundary for the GenAI conventions.
- Six detection rules: span errors, tool loops, and outliers in latency and
  tokens, per trace and per span, with thresholds settable per rule.
- Idempotent incidents in PostgreSQL with a probable cause and a signature.
- Alerts by generic webhook, Slack, Google Chat and Teams, with a per-channel
  outbox and retry.
- Human labels, a JSONL export of evals, an Anthropic judge adapter and a
  command that measures Cohen's kappa.
- An HTTP API with a bearer token.
- Versioned schema migrations, a worker checkpoint, a leader lock, sharding by
  trace id, a readiness probe and Prometheus metrics.
- A container image, Docker Compose services and Kustomize manifests for
  Kubernetes, with an optional bearer token on the OTLP receiver.

### Known limits

- Thresholds were calibrated on simulated data only.
- The Kubernetes tests ran on one local node with throwaway databases.
- The OTLP token is shared and travels in clear text without TLS.
- There is no web interface and no published container image.

See the architecture decisions in [docs/adr](docs/adr/README.md).
