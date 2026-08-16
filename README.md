# Design Drift

**Autonomous AI Design QA & Remediation Platform.**

Design Drift compares a Figma design against a real, deployed (or local)
web application, detects drift in visual appearance, layout, typography,
color, responsive behavior, component structure, accessibility, and
interaction behavior — then proposes and (with human approval) applies a
code fix, verifies it, and reports before/after results.

This repository is being built incrementally as a learning project for AI
engineering: LangGraph multi-agent workflows, structured LLM outputs,
multimodal reasoning, tool calling, human-in-the-loop control, RAG, and
evaluation — layered on top of a conventional, production-shaped
full-stack app (FastAPI + PostgreSQL + React/TypeScript).

> **Status:** Phase 1 — Figma integration. A project (Figma file/node +
> target app URL) can be registered via the API or the frontend panel; the
> backend fetches and stores the node's styles/layout/hierarchy and a
> rendered screenshot from the real Figma REST API. No Playwright,
> visual/production comparison, or LLM/agent reasoning yet — see
> [`docs/architecture.md`](docs/architecture.md) for the target
> architecture and [`docs/principles.md`](docs/principles.md) for the
> engineering ground rules this project follows.

## Repository layout

```
design-drift/
├── frontend/     React + TypeScript + Vite + Tailwind UI
├── backend/      Python + FastAPI + SQLAlchemy + PostgreSQL API
├── docs/         Architecture and engineering principles
├── infra/docker/ Local development Docker Compose stack
├── samples/      Sample Figma/production fixtures used for manual testing
└── .claude/      Claude Code development-agent configuration (see below)
```

## Local development

Prerequisites: Docker, Node.js 20+, Python 3.12+, [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
# Set FIGMA_ACCESS_TOKEN in .env to fetch real Figma data (a personal
# access token: https://www.figma.com/developers/api#access-tokens).
# Project registration works without it but returns a 502.

# Start PostgreSQL (and, once added, other infra) via Docker
docker compose -f infra/docker/docker-compose.yml up -d postgres

# Backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173
Backend health check: http://localhost:8000/api/v1/health

Full setup, testing, and linting instructions live in
[`backend/README.md`](backend/README.md) and
[`frontend/README.md`](frontend/README.md).

## Claude Code development agents

This repo defines a small set of Claude Code subagents (in `.claude/agents/`)
scoped to **building** Design Drift — they are development tooling, not part
of the shipped product:

- `architecture-agent` — architecture, boundaries, data-flow review
- `backend-agent` — FastAPI, Pydantic, persistence, APIs, SSE
- `ai-agent` — LangGraph, LLM integration, runtime agents, evals
- `frontend-agent` — React/TypeScript UI, state, SSE integration
- `browser-agent` — Playwright, screenshots, DOM extraction, accessibility
- `test-review-agent` — implementation review and test coverage

These are distinct from the **runtime agents Design Drift itself executes**
(Supervisor, Design Analysis, Production Analysis, Visual Comparison,
Accessibility, Code Analysis, Fix, Verification), which are documented in
`docs/architecture.md`.

## Git / PR policy

This project (both as a product and in how it's built) never automatically
pushes, merges, or opens pull requests. Commits are prepared locally; the
repository owner reviews and pushes manually.
