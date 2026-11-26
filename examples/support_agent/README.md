# Support agent example

A small customer-support agent that produces OpenTelemetry GenAI traces for
Rolda. It handles "where is my order", "refund" and "change address"
requests.

The model is simulated. A scripted, seeded stand-in returns plausible token
counts and sleeps for a log-normal latency. There is no API key and no
network LLM call. The tools (`search_orders`, `get_refund_policy`,
`issue_refund`, `update_address`) and the agent control flow are real code.

Each session emits an `invoke_agent support-agent` root span, `chat <model>`
spans and `execute_tool <name>` spans, with `service.name=support-agent`.

Faults are injected per session, about: 8% tool timeouts, 3% rate limits
(429), 4% tool loops (same tool and arguments 6-10 times), 3% latency
outliers (3-6x slower model call) and 3% token blowups (5-10x input
tokens). The timeout error says "timeout after 30s" but does not wait 30
seconds.

## Run

The dependencies are not part of `pyproject.toml`. Use an ephemeral
environment, with an OTLP/HTTP collector on `127.0.0.1:4318`:

```bash
uv run --no-project \
  --with opentelemetry-sdk \
  --with opentelemetry-exporter-otlp-proto-http \
  python examples/support_agent/run.py
```

Options: `--sessions` (default 300), `--seed`, `--endpoint`, `--min-gap`,
`--max-gap`. Sessions are spaced by random gaps, so 300 sessions take
several minutes. A summary of the injected faults prints at the end.
