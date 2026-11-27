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

### Detection thresholds

The outlier rules use a robust z-score. The defaults come from runs on
simulated data (see `docs/adr/0009-redundant-outliers-and-span-latency.md`).
Re-check them on your own traces. All variables are optional; an invalid
value stops the worker at start.

| Variable | Default | Meaning |
|---|---|---|
| `ROLDA_Z_THRESHOLD` | 3.5 | Shared threshold for rules without their own value |
| `ROLDA_Z_LATENCY` | shared | Whole-trace latency rule only |
| `ROLDA_Z_SPAN_LATENCY` | 3.0 | Slow model or tool call |
| `ROLDA_Z_TOKENS` | shared | Token usage of a whole trace |
| `ROLDA_Z_SPAN_TOKENS` | shared | One model call with far more tokens than usual |
| `ROLDA_MIN_SAMPLES` | 30 | History needed before an outlier rule runs (at least 1) |
| `ROLDA_TOOL_LOOP_REPEATS` | 3 | Same tool and arguments this many times is a loop (at least 2) |

Lower values catch more and raise more false alarms.

## Running the worker and API in containers

For development, one command starts the databases, the Collector, the worker
and the API. Add `ROLDA_API_TOKEN` (at least 16 characters) to
`deploy/compose/.env` first:

```bash
cd deploy/compose
docker compose --profile app up -d --build
curl http://127.0.0.1:8000/health
```

If port 8000 is taken, set `ROLDA_API_HOST_PORT` (for example 8001).
`docker compose up` without `--profile app` still starts only the
infrastructure. The API is published on `127.0.0.1` only. See
`docs/adr/0011-container-image.md`.

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

## Measuring the judge

After labeling enough incidents (at least 30), measure how well the judge
agrees with you:

```bash
export ANTHROPIC_API_KEY=...   # never commit it
uv run python -m rolda.entrypoints.cli judge-eval --evals evals.jsonl
```

It prints Cohen's kappa, agreement, the confusion counts and how many
answers were `uncertain` (left out of kappa). The model defaults to
`claude-haiku-5-5`; set `ROLDA_JUDGE_MODEL` to change it. The judge sees
trace behavior only. See `docs/adr/0008-judge-and-kappa.md`. No kappa value
is published yet: it needs real human labels.

## HTTP API

The API lists incidents, shows a trace's behavior, records human labels and
exports the eval file. Everything except `/health` needs a bearer token.

```bash
export ROLDA_API_TOKEN=...   # at least 16 characters, never commit it
set -a && . deploy/compose/.env && set +a
uv run python -m rolda.entrypoints.api_main
curl -H "Authorization: Bearer $ROLDA_API_TOKEN" \
  "http://127.0.0.1:8000/incidents?limit=10"
```

It listens on `127.0.0.1:8000`. Change that with `ROLDA_API_HOST` and
`ROLDA_API_PORT`, and put TLS in front before you expose it. Set
`ROLDA_API_DOCS=true` to serve the OpenAPI docs. See
`docs/adr/0010-http-api.md`.
