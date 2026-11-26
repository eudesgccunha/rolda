# 0006. Alerts and probable cause

Status: accepted

## Context

M4 needs a probable cause per incident and an alert when a new incident
appears. Trace content is untrusted and reaches alert channels.

## Decision

- The probable cause is a hypothesis: the span path from the trace root to
  the span behind the finding, plus a signature
  `agent|rule|operation|normalized error`. The agent is the trace root's
  agent. Error messages lose ids, numbers and `|`, and are cut at 80
  characters, so similar errors share a signature.
- `Alerter` is a port. Adapters: a generic JSON webhook and a Slack
  incoming webhook, both on the standard library (`http.client`).
- The worker alerts only when `IncidentStore.save` reports a new incident,
  so reprocessing a window does not resend alerts.
- A failed delivery is logged and the worker goes on. The alert is not
  retried. Incidents stay in the store, so nothing is lost silently.
- Slack text escapes `&`, `<` and `>` and cuts the hypothesis at 500
  characters, so trace content cannot mention a channel or inject links.
- Webhook URLs come from the environment, must be http or https with a
  host, and are optional.

## Consequences

- An alert lost to a down channel is not resent. Revisit with an
  `alerted_at` column and a retry, or an outbox, when this matters.
- Outbound webhooks are an operator choice. Restrict the destination at
  the network level when running in shared infrastructure.
