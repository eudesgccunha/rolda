# Running Rolda on Kubernetes

`base/` holds the Rolda pieces: the API, the worker, the OpenTelemetry
Collector, the network policies and the settings. It does **not** include the
databases. Point `rolda-config` at your ClickHouse and PostgreSQL (an operator
or a managed service) and create the Secret `rolda-secrets` from
`base/secrets.example.yaml`, with values from your secret manager.

```bash
# 1. Build or pull the image and set it in your own overlay:
#    images: [{name: rolda, newName: your.registry/rolda, newTag: "0.1.0"}]
# 2. Create the namespace and the Secret.
# 3. Apply:
kubectl apply -k your-overlay
```

There is no published image yet. Build it from `deploy/docker/Dockerfile`.

## What it does

- The API runs 2 replicas with a liveness probe on `/health` and a readiness
  probe on `/ready` (both databases). A PodDisruptionBudget keeps one up.
- The worker is a StatefulSet. The pod ordinal is the shard index, so
  `ROLDA_SHARD_INDEX=auto`. To add throughput, raise `replicas` **and**
  `ROLDA_SHARD_COUNT` in `rolda-config` together (ADR 0019). Each shard keeps its
  own checkpoint and lock, so a replaced pod resumes where it stopped.
- Each pod runs the schema migration in an init container. It is idempotent and
  locked, so several pods starting together are safe.
- The Collector is a StatefulSet of 2. Each pod keeps its queue on its own
  volume (`otelcol.yaml`), so spans accepted before a pod dies or ClickHouse is
  down are sent later.
- Pods run as a non-root user with a read-only root filesystem, no
  capabilities and the `RuntimeDefault` seccomp profile. The namespace enforces
  the `restricted` Pod Security level.
- Ingress is denied by default. The policies allow OTLP to the Collector, port
  8000 to the API and port 9100 to the worker. Narrow their `from` to your
  agents, your ingress controller and Prometheus. Egress is not restricted.

## Not included

- The databases (see above), TLS, an Ingress, and authentication of the OTLP
  receiver. Put the Collector behind your mesh or gateway if agents are not
  inside the cluster.
- A metrics scraper. The worker serves Prometheus text on `:9100/metrics`.

## Try it locally

`overlays/dev` adds throwaway databases so everything runs in a
[kind](https://kind.sigs.k8s.io) cluster. `examples/k8s/kill_test.sh` creates
the cluster, sends a batch of simulated agent sessions and deletes pods in the
middle. Do not use the dev overlay for anything real: its databases are not
replicated.
