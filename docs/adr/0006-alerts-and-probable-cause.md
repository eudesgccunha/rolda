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
- `Alerter` is a port. Adapters: a generic JSON webhook, Slack, Google
  Chat and Microsoft Teams, all on one `http.client` transport.
- Teams uses a Workflows webhook with an Adaptive Card, because Office 365
  connector webhooks were retired in May 2026.
- The worker alerts only when `IncidentStore.save` reports a new incident,
  so reprocessing a window does not resend alerts.
- A failed delivery is logged and the worker goes on. The alert is not
  retried. Incidents stay in the store, so nothing is lost silently.
- Each channel neutralizes trace content: Slack escapes `&`, `<` and `>`,
  Google Chat swaps angle brackets for look-alikes (no escape is
  documented), and Teams removes `[`, `]` and backticks. The hypothesis
  is cut at 500 characters.
- The Google Chat and Teams formats are checked against local servers
  only, not against the real services.
- Webhook URLs come from the environment, must be http or https with a
  host, and are optional.

## Consequences

- An alert lost to a down channel is not resent. Revisit with an
  `alerted_at` column and a retry, or an outbox, when this matters.
- Outbound webhooks are an operator choice. Restrict the destination at
  the network level when running in shared infrastructure.
