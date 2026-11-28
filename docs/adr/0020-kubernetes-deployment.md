# 0020. Kubernetes deployment

## Status

Accepted.

## Context

The M8 assessment asked whether Kubernetes could keep Rolda up. The worker
state, the schema and the Collector queue had to stop depending on one
process or one disk first.

## Decision

- Manifests are plain Kustomize (`deploy/k8s`), not Helm: no templating to
  learn, and a user overlay can set the image and the settings. A base holds
  Rolda only. The databases are the user's (operator or managed service). A
  `dev` overlay adds throwaway databases for local tests.
- The worker is a StatefulSet whose pod ordinal is its shard (ADR 0019).
  Checkpoint and lock are per shard (ADR 0013), so a rescheduled pod resumes.
- Migrations run in an init container of the API and worker pods
  (ADR 0012). A separate Job was not needed, because the runner is idempotent
  and holds a lock.
- The Collector is a StatefulSet with a disk queue and unlimited retry to
  ClickHouse, so a restart or a ClickHouse outage does not drop accepted spans.
- Pods set `enableServiceLinks: false`. Kubernetes otherwise injects
  `ROLDA_API_PORT=tcp://...` for a Service named `rolda-api`, which overwrote
  our own setting and stopped the API. A test checks every pod spec.
- Images are pinned by digest, like Compose. Pod security is `restricted`.

## Evidence

On a local one-node kind cluster (Kubernetes 1.37) with the dev overlay:

- 200 simulated agent sessions with pods deleted in the middle (the worker
  once gracefully and once by force, one Collector pod, the PostgreSQL pod).
  All 16 timeouts, 6 rate limits and 8 loops were found, no healthy session was
  flagged and no incident was duplicated.
- Two shards (two worker pods): each led its own shard, the incidents split 6
  and 7 as `crc32(trace_id) % 2` predicts, 13 of 13 were found, none repeated.

## Consequences

- This was one node, throwaway databases and a small load. It shows that the
  design recovers from the pod failures tried. It is not a test of a real
  cluster: multiple nodes, node loss, network partitions, storage failure and
  a database outage were not tried.
- The first run found two mistakes only Kubernetes could show: the Service
  link variables, and databases created in the wrong namespace by the overlay.
- The OTLP receiver has no authentication. Anything that can reach the
  Collector can write spans.
- A shard that falls below `ROLDA_MIN_SAMPLES` for a small agent gets no
  outlier rules (ADR 0019).
