# Design Drift — Backend

FastAPI + SQLAlchemy (async) + PostgreSQL. Python 3.12+, managed with
[uv](https://docs.astral.sh/uv/).

## Setup

```bash
cd backend
uv sync                      # creates .venv, installs deps + dev deps
```

Copy `../.env.example` to `../.env` (repo root) and adjust as needed —
`Settings` reads it via `pydantic-settings`.

## Run

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Health check: `GET http://localhost:8000/api/v1/health`

## Test / lint / typecheck

```bash
uv run pytest
uv run ruff check .
uv run mypy app
```

## Layout

See `../docs/architecture.md` for the full rationale. In short:
`api/` (routers) → `services/` (logic, added as needed) → `db/`/`models/`
(persistence). `agents/`, `graph/`, `tools/`, `integrations/`, `evals/` are
added starting Phase 1–3 when Figma/Playwright/LangGraph work begins —
they don't exist yet on purpose.
