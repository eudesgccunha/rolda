# Rolda

Open source, self-hosted observability for AI agents in production.

Status: early development. See [docs/SPEC.md](docs/SPEC.md).

## Development

```bash
uv sync --locked
uv run pytest
```

Coding agents: follow [AGENTS.md](AGENTS.md).

## Running locally

Needs Docker with Compose.

```bash
cd deploy/compose
cp .env.example .env   # then set a real CLICKHOUSE_PASSWORD
docker compose up -d --wait
```

The Collector listens on `127.0.0.1:4317` (gRPC) and `127.0.0.1:4318`
(HTTP). ClickHouse listens on `127.0.0.1:8123` and `127.0.0.1:9000`.

Integration test (needs the stack running):

```bash
set -a && . deploy/compose/.env && set +a
uv run pytest -m integration
```

## Running the worker

With the stack up and the variables from `deploy/compose/.env` exported:

```bash
set -a && . deploy/compose/.env && set +a
uv run python -m rolda.entrypoints
```

Optional variables: `ROLDA_CLICKHOUSE_HOST`, `ROLDA_CLICKHOUSE_PORT`,
`ROLDA_POSTGRES_HOST`, `ROLDA_POSTGRES_PORT`, `ROLDA_WINDOW_SECONDS`
(default 300) and `ROLDA_INTERVAL_SECONDS` (default 60).

Alerts are sent for new incidents to every channel whose URL is set. Each
must be an http or https URL:

| Variable | Channel |
|---|---|
| `ROLDA_WEBHOOK_URL` | Generic JSON webhook |
| `ROLDA_SLACK_WEBHOOK_URL` | Slack incoming webhook |
| `ROLDA_GOOGLE_CHAT_WEBHOOK_URL` | Google Chat incoming webhook |
| `ROLDA_TEAMS_WEBHOOK_URL` | Teams Workflows webhook (Adaptive Card) |

Webhook URLs hold secrets. Keep them in the environment, never in the
repository. Rolda does not log them.

## Labeling and evals

Label an incident, then export the labeled set as a regression file:

```bash
uv run python -m rolda.entrypoints.cli label <trace_id> <rule> failure --reason "real outage"
uv run python -m rolda.entrypoints.cli export-evals --out evals.jsonl
```

Verdicts: `failure`, `false_alarm`, `uncertain` (not exported). The export
holds trace behavior only, never prompt or response content. See
`docs/adr/0007-eval-export.md`. Both commands need `POSTGRES_*` (and
`CLICKHOUSE_*` for the export) in the environment.
