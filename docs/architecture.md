# Architecture

This document describes the target architecture for Design Drift. It will
grow as each phase lands; sections marked **(not yet built)** describe
where we're heading, not what exists today.

## System overview

```
                         ┌─────────────────────────┐
                         │   Figma REST API         │
                         └───────────┬──────────────┘
                                     │
┌────────────┐   REST + SSE   ┌──────▼──────┐   Playwright   ┌──────────────┐
│  Frontend    │◄─────────────►│   Backend    │───────────────►│ Target web   │
│  React/TS    │                │   FastAPI    │                │ app under    │
│  (Vite)      │                │              │                │ test         │
└──────────────┘                └──────┬──────┘                └──────────────┘
                                        │
                              ┌─────────▼─────────┐
                              │ LangGraph workflow │  (not yet built)
                              │ (runtime agents)   │
                              └─────────┬─────────┘
                                        │
                              ┌─────────▼─────────┐
                              │ PostgreSQL +        │
                              │ artifact storage     │
                              └──────────────────────┘
```

## Why Vite, not Next.js

The product is an authenticated, dashboard-style developer tool — comparison
views, overlays, live agent progress — with no public marketing pages and no
SEO requirement. All data comes from our own FastAPI backend over REST/SSE,
so there's no benefit to Next.js's server rendering, file-based routing, or
API routes; they'd just be a second server to reason about next to FastAPI.
Vite + React Router gives a fast dev loop and a plain static build we can
serve from anywhere, with one clear backend (FastAPI) doing all the work.
We'll revisit this only if a concrete need for SSR/SEO appears.

## Backend structure

The backend uses a pragmatic subset of the "full" layered structure —
folders are added when a phase actually needs them, not up front:

```
backend/app/
├── api/          FastAPI routers, versioned (api/v1/...)
├── core/         Settings, logging, app-wide config
├── db/           SQLAlchemy engine/session, declarative base
├── models/       SQLAlchemy ORM models          (added when we persist data)
├── schemas/      Pydantic request/response models (added as endpoints need them)
├── services/     Business logic, orchestration    (added when logic exists beyond routing)
├── agents/       LangGraph runtime agents          (Design Analysis + Production Analysis + Visual Comparison + Supervisor built — Phase 3)
├── graph/        LangGraph graph definition/state   (Design Analysis + Production Analysis + Visual Comparison workflow built — Phase 3)
├── tools/        Agent tool implementations          (not yet built — Phase 3+)
├── integrations/ Figma, Playwright, axe-core clients  (not yet built — Phase 1+)
└── evals/        AI evaluation harness                (not yet built — Phase 8)
```

We are deliberately **not** creating `repositories/` as a separate
persistence-abstraction layer yet — with a single database and
straightforward query patterns, SQLAlchemy sessions used directly from
`services/` are simpler to read and debug. We'll introduce a repository
layer only if query logic starts duplicating across services.

## Runtime multi-agent workflow (Design Analysis + Production Analysis + Visual Comparison vertical slices built)

Design Drift's own agents (distinct from the Claude Code agents used to
*build* this repo — see `.claude/agents/`) are implemented as LangGraph
nodes operating on one shared, structured state object — not by passing
free-form natural-language messages between agents.

The Supervisor, Design Analysis Agent, Production Analysis Agent, and
Visual Comparison Agent are wired up so far (`app/graph/workflow.py`,
`app/agents/`): `START -> supervisor -> (design_analysis -> supervisor)*
-> (production_analysis -> supervisor)* -> (visual_comparison ->
supervisor)* -> END`, all exposed together via one `POST
/api/v1/projects/{project_id}/design-analysis` call. Two caveats against
the target table below: Production Analysis today only covers the
"screenshot" half of its planned tool set (no DOM/computed-style
extraction yet), and this graph's Visual Comparison doesn't yet fold in
accessibility context the way `app/services/reviews.py`'s older,
Scan-scoped version does — the Accessibility Agent isn't wired into this
graph yet, so there's nothing to fold in. Both `app/services/reviews.py`
(Scan-scoped) and this graph's Visual Comparison node (Project-scoped)
exist side by side for now, rather than one replacing the other. The
diagram below is the target shape once the remaining agents land — each
new one extends the Supervisor's routing rather than inventing its own
graph.

```
START
  → initialize scan
  → analyze Figma            (Design Analysis Agent)
  → analyze production       (Production Analysis Agent)
  → compare                  (Visual Comparison Agent)
  → accessibility analysis   (Accessibility Agent)
  → aggregate findings
  → route: problems found?
      no  → finalize report → END
      yes → code analysis    (Code Analysis Agent)
          → propose fix      (Fix Agent)
          → [PAUSE: human review]
              rejected → finalize report → END
              approved → apply fix locally
                       → verify              (Verification Agent)
                       → before/after compare
                       → finalize report → END
```

Planned agents, each with a defined responsibility, inputs/outputs (as
Pydantic models), available tools, and the slice of shared state it may
read/write:

| Agent | Responsibility | Key tools |
|---|---|---|
| Supervisor | Owns workflow state, routes between agents | none (pure routing) |
| Design Analysis | Interpret Figma structure/styles/intent | Figma REST API, multimodal LLM |
| Production Analysis | Inspect the real app | Playwright (screenshots ✅, DOM/computed styles not yet built) |
| Visual Comparison | Expected vs. actual → structured drift findings | image diffing ✅, multimodal LLM ✅ |
| Accessibility | Deterministic a11y violations + AI interpretation | axe-core, LLM (interpretation only) |
| Code Analysis | Map findings to likely source files | repo search/grep, LLM |
| Fix Agent | Propose a code patch (never applies/publishes) | LLM structured output |
| Verification | Re-run checks after a fix, before/after compare | Playwright, axe-core, image diffing |

We are *not* splitting these further (e.g. separate "screenshot agent" vs.
"DOM agent") because that would add coordination overhead without adding a
decision that needs its own autonomy — Production Analysis can call
Playwright tools directly as deterministic steps within one agent.

## Avoiding "fake AI"

Deterministic tasks use deterministic tools, not LLM calls:

- Element geometry, CSS values, navigation, screenshots → Playwright/DOM APIs
- Accessibility rule violations → axe-core
- Pixel-level image comparison → image processing (not vision reasoning)

The LLM (multimodal where relevant) is reserved for judgment calls that
genuinely need reasoning: interpreting design *intent*, deciding whether a
visual difference is material, reasoning about component relationships, and
proposing a remediation.

## Communication

REST for request/response; **Server-Sent Events** for streaming live scan/
agent progress from FastAPI to the frontend. We're not using WebSockets —
progress only flows server → client, so SSE is the simpler, sufficient
choice; this is revisited only if the frontend genuinely needs to push data
back mid-stream.

## Human-in-the-loop (not yet built)

The LangGraph workflow pauses (via checkpointing) before applying a code
fix. The frontend surfaces Approve / Reject / Request another solution /
Inspect diff controls. The backend never auto-applies a fix, and the
product never creates, merges, or pushes a GitHub pull request — the repo
owner (not the running application) handles Git operations.

## Storage (Phase 0)

- **PostgreSQL** — application/workflow data (projects, scans, findings).
- **Local filesystem, behind a small storage abstraction** — screenshots
  and other artifacts, so we can swap in S3 later without touching callers.

Redis, a vector store, and RAG are deferred until a concrete phase needs
them (Phase 7 for RAG) rather than added speculatively.
