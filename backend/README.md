# Design Drift — Backend

FastAPI + SQLAlchemy (async) + PostgreSQL. Python 3.12+, managed with
[uv](https://docs.astral.sh/uv/).

## Setup

```bash
cd backend
uv sync                      # creates .venv, installs deps + dev deps
uv run playwright install chromium   # browser binary for production capture/scans
```

Copy `../.env.example` to `../.env` (repo root) and adjust as needed —
`Settings` reads it via `pydantic-settings`. Set `FIGMA_ACCESS_TOKEN` (a
[Figma personal access token](https://www.figma.com/developers/api#access-tokens))
if you want project registration (`POST /api/v1/projects`) to actually
fetch design data — without it, registration fails with a 502.

Start Postgres (published on host port `55432` by default — see
`POSTGRES_HOST_PORT` in `.env.example`; some machines already run a native
Postgres on 5432/5433, which this avoids colliding with):

```bash
docker compose -f ../infra/docker/docker-compose.yml up -d postgres
```

Apply migrations:

```bash
uv run alembic upgrade head
```

## Run

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Health check: `GET http://localhost:8000/api/v1/health`

## Test / lint / typecheck

```bash
uv run pytest        # API tests hit the real local Postgres above; scan
                      # tests also launch a real (headless) browser
uv run ruff check .
uv run mypy app
```

## Migrations

```bash
uv run alembic revision --autogenerate -m "..."   # after changing a model
uv run alembic upgrade head
uv run alembic downgrade -1                        # roll back one revision
```

## Layout

See `../docs/architecture.md` for the full rationale. In short:
`api/` (routers) → `services/` (logic) → `db/`/`models/` (persistence),
with request/response shapes in `schemas/` and typed models in
`integrations/` (`figma/`, `storage/`, `playwright/` — production capture,
`imaging/` — deterministic pixel diffing). `agents/`, `graph/`, `tools/`,
`evals/` are added starting Phase 3+ when LangGraph work begins — they
don't exist yet on purpose.
