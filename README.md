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
