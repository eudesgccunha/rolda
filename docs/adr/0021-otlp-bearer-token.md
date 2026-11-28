# 0021. Bearer token on the OTLP receiver

## Status

Accepted.

## Context

The OTLP receiver accepted writes from anyone who could reach it. Compose binds
it to `127.0.0.1`, which is enough on one machine, but in Kubernetes agents
reach the Collector across the network, and anything that can reach it could
write spans (and so create incidents).

## Decision

- The Collector's `bearertokenauth` extension guards both OTLP protocols (gRPC
  and HTTP). A write without `Authorization: Bearer <ROLDA_OTLP_TOKEN>` is
  refused with 401.
- Kubernetes: on by default. The token comes from the Secret `rolda-secrets`
  (key `ROLDA_OTLP_TOKEN`), and the pod does not start without it.
- Compose: off by default, so the existing local setup keeps working. Set
  `COLLECTOR_CONFIG=collector.auth.yaml` and `ROLDA_OTLP_TOKEN` to turn it on.
- Agents send the header. With the OpenTelemetry SDKs that is
  `OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer%20<token>"`.

## Evidence

A real Collector (`tests/integration/test_collector_auth.py`): no token, a wrong
token and a wrong scheme are all refused with 401, and the right token gets
200. The Python SDK of the simulated agent works with the header. Both shipped
configs pass the Collector's own `validate`. The Kubernetes test (ADR 0020)
runs with the token on.

## Consequences

- The scheme is case sensitive: `bearer` in lower case is refused.
- One shared token for every agent. It cannot tell agents apart or be revoked
  for one of them. Rotate it by changing the Secret and restarting the
  Collector, then the agents.
- The token travels in clear text unless the connection uses TLS. This
  decision does not add TLS. Put the Collector behind a mesh or gateway that
  does, or add TLS to the receiver.
