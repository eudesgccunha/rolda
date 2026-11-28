# Architecture decision records

| ADR | Decision |
|---|---|
| [0001](0001-languages.md) | Languages: Python for the core, TypeScript for the UI |
| [0002](0002-clickhouse-span-schema.md) | ClickHouse span schema |
| [0003](0003-normalization-boundary.md) | Raw OpenTelemetry attributes are read in one place only |
| [0004](0004-idempotent-incidents.md) | Idempotent incidents and the window lag |
| [0005](0005-persistence-adapters.md) | Persistence adapters and the worker process |
| [0006](0006-alerts-and-probable-cause.md) | Alert channels and the probable cause |
| [0007](0007-eval-export.md) | Eval export from human labels |
| [0008](0008-judge-and-kappa.md) | Judge adapter and kappa measurement |
| [0009](0009-redundant-outliers-and-span-latency.md) | Redundant outliers, per-span rules and calibration |
| [0010](0010-http-api.md) | HTTP API |
| [0011](0011-container-image.md) | Container image and Compose services |
| [0012](0012-schema-migrations.md) | Versioned schema migrations |
| [0013](0013-worker-checkpoint-and-leadership.md) | Worker checkpoint and leader lock |
| [0014](0014-alert-outbox.md) | Alert outbox |
| [0015](0015-zero-mad-fallback.md) | Outlier score when the MAD is zero |
| [0016](0016-probes-and-metrics.md) | Probes and metrics |
| [0017](0017-baseline-from-slices.md) | Baseline built from slices, in the background |
| [0018](0018-connection-pool-and-agent-column.md) | Connection pool and an indexed agent column |
| [0019](0019-sharding.md) | Sharding the worker by trace id |
| [0020](0020-kubernetes-deployment.md) | Kubernetes deployment |

Add a new record as `NNNN-title.md` when a decision changes the architecture,
a dependency or a security property.
