# Contributing to Rolda

Thanks for your interest. Rolda is pre-release, so the most useful
contributions right now are bug reports, traces from real agents (with
content removed) and small, well-tested changes.

## Set up

You need Python 3.12 or newer, [uv](https://docs.astral.sh/uv/) and, for the
integration tests, Docker with Compose.

```bash
uv sync --locked
uv run ruff format --check . && uv run ruff check .
uv run mypy && uv run bandit -c pyproject.toml -r src
uv run pytest
```

All of these must pass before you open a pull request. CI runs the same
commands on Python 3.12.

The integration tests need the Compose stack and its environment variables:

```bash
cd deploy/compose && cp .env.example .env   # set real values
docker compose up -d --wait
cd ../.. && set -a && . deploy/compose/.env && set +a
uv run pytest -m integration
```

## How to work

1. Open an issue for anything bigger than a small fix, so we agree on the
   approach first.
2. Branch from `develop`. Open the pull request against `develop`.
3. Write the failing test first, then the smallest change that passes it.
4. Keep pull requests small, ideally under 400 changed lines.
5. If the change affects the architecture, a dependency or a security
   property, add an ADR in `docs/adr/` and list it in `docs/adr/README.md`.
6. If you change what is built or verified, update `docs/STATUS.md`.

## Rules that are not negotiable

- Domain code does not import FastAPI, database drivers or LLM SDKs.
  Adapters do, and they are wired at the entry points.
- Raw OpenTelemetry attributes are read only in `traces/normalize.py`.
- Trace content is untrusted input. Never execute it, and give it to the
  judge only as delimited data.
- No secrets in the repository. Use environment variables.
- Parameterized queries only.
- Do not weaken lint, type, security or test settings, and do not skip or
  delete a failing test to get CI green.
- Ask before adding a dependency, and commit `uv.lock` with it.
- Pin GitHub Actions and container images by digest or commit SHA.

## Reporting security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).

## Working with coding agents

[AGENTS.md](AGENTS.md) holds the rules for coding agents. They apply to
humans too.
