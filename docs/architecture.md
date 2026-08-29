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
├── agents/       LangGraph runtime nodes            (Supervisor + four inspection agents + aggregation + Code Analysis built — Phase 3)
├── graph/        LangGraph graph definition/state   (workflow through Code Analysis built — Phase 3)
├── tools/        Agent tool implementations          (repo_search + anchors built — Phase 3)
├── integrations/ Figma, Playwright, axe-core clients  (not yet built — Phase 1+)
└── evals/        AI evaluation harness                (not yet built — Phase 8)
```

We are deliberately **not** creating `repositories/` as a separate
persistence-abstraction layer yet — with a single database and
straightforward query patterns, SQLAlchemy sessions used directly from
`services/` are simpler to read and debug. We'll introduce a repository
layer only if query logic starts duplicating across services.

## Runtime multi-agent workflow (inspection agents + aggregation + Code Analysis built)

Design Drift's own agents (distinct from the Claude Code agents used to
*build* this repo — see `.claude/agents/`) are implemented as LangGraph
nodes operating on one shared, structured state object — not by passing
free-form natural-language messages between agents.

The Supervisor, all four inspection agents (Design Analysis, Production
Analysis, Visual Comparison, Accessibility), the findings aggregation, and
the Code Analysis Agent are wired up so far (`app/graph/workflow.py`,
`app/agents/`): `START -> supervisor -> (design_analysis -> supervisor)*
-> (production_analysis -> supervisor)* -> (visual_comparison ->
supervisor)* -> (accessibility -> supervisor)* -> (aggregate_findings ->
supervisor)* -> (code_analysis -> supervisor)? -> END`, all exposed
together via one `POST /api/v1/projects/{project_id}/design-analysis`
call.

Note the `?`: every node before Code Analysis always runs, but Code
Analysis is `route: problems found?` — a real fork, taken only when the
aggregation found problems *and* the project has a source checkout
configured (`Project.source_path`). A project without one still gets every
inspection agent and simply ends after aggregation.

That covers the target flow below through `code analysis`. What remains —
Fix Agent, Verification, human-in-the-loop — is the part that proposes and
validates changes rather than diagnosing them.

Caveats against the target table below:

- **Code Analysis retrieves before it reasons.** Deterministic anchors
  (ids, class names, accessible names, visible text) come out of what the
  inspection agents observed — mostly axe-core's per-violation DOM
  evidence — via `app/tools/anchors.py`; a content search over the
  checkout ranks files by how much of that evidence they contain and
  returns snippets with real line numbers; only then does the LLM pick the
  location. Output is one file/line range per finding with quoted
  evidence, or an explicit `no_match`.
- **It is not a tool-use loop.** The model sees the candidates the search
  chose and cannot request more files. That keeps every node on the same
  single structured call, and keeps the set of files that can reach an LLM
  API decided by our code rather than by the model — which matters when
  those files come from a user-configured path. A real
  search→read→refine loop would locate more, and is the next step up.
- **Anchor quality is uneven, by design.** Accessibility findings carry a
  hard link to real DOM, so their anchors are strong. Visual findings are
  prose about two images, so they yield weaker signals: quoted literals
  (decoration stripped — a rendered "Links ->" is the word `Links` plus a
  CSS arrow), title-case section names lifted from unquoted prose
  ("Schedule of Events"), and the project's target selector. Those two
  prose-derived kinds rank below DOM evidence deliberately. A finding that
  offers none of them still returns `no_match` rather than a guess. The
  real fix remains Production Analysis extracting the DOM alongside its
  screenshot (still not built).
- **Document-level rules anchor on the element itself.** `html-has-lang`
  and the landmark rules target a bare `<html>`/`<body>`, which carries no
  id or class. A tag anchor (weakest weight, matched as markup so prose
  mentions of "html" don't count) points at the right file instead of
  returning nothing — but only for structural tags, since a bare `div`
  identifies nothing.
- **Source checkouts are confined.** `Project.source_path` resolves
  *relative to* `Settings.source_root` and is rejected if it escapes it
  (`..`, absolute paths, or symlinks pointing out). These files get sent to
  a third-party LLM API, so an unconstrained path would turn a project
  field into arbitrary file read plus exfiltration.
- **Production Analysis** covers only the "screenshot" half of its planned
  tool set — no DOM/computed-style extraction yet. It captures at the
  Figma frame's own width (`match_figma_viewport`, shared with scans),
  falling back to 1280x800 only when the node records no width: this
  capture exists to be diffed against that render, so a width mismatch
  would manufacture layout drift the target app never had.
- **Visual Comparison** here doesn't fold accessibility context into its
  own judgment the way `app/services/reviews.py`'s older, Scan-scoped
  version does; Accessibility runs as its own separate node/judgment
  instead, and the two are merged afterwards by `aggregate_findings`.
- **Accessibility** skips its LLM call entirely when axe-core finds zero
  violations (nothing to interpret).
- Both `app/services/reviews.py` (Scan-scoped) and this graph's Visual
  Comparison node (Project-scoped) exist side by side for now, rather than
  one replacing the other. The frontend surfaces them separately too:
  `DesignQAPanel` (project-level) runs this graph, while `ScanSection`
  keeps the older per-scan diff and review.

The diagram below is the target shape once the remaining agents land —
each new one extends the Supervisor's routing rather than inventing its
own graph.

```
START
  → initialize scan
  → analyze Figma            (Design Analysis Agent)
  → analyze production       (Production Analysis Agent)
  → compare                  (Visual Comparison Agent)
  → accessibility analysis   (Accessibility Agent)
  → aggregate findings       (deterministic — merge/triage, no LLM)
  → route: problems found?   (also skipped when no source checkout is set)
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
| Accessibility | Deterministic a11y violations + AI interpretation | axe-core ✅, LLM (interpretation only) ✅ |
| Code Analysis | Map findings to exact source locations | repo content search ✅, LLM ✅ |
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
- Merging/sorting findings the agents already judged → plain Python
  (`app/agents/aggregate_findings.py`); re-asking a model to combine two
  lists it just produced would add cost and nondeterminism for nothing

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

## Source-code access

The Code Analysis Agent (and later the Fix Agent) needs the target app's
source. Two constraints on that, both enforced in
`app/tools/repo_search.py`:

- **Confined.** `Project.source_path` is resolved relative to
  `Settings.source_root` and rejected if it escapes — absolute paths, `..`
  segments, and symlinks pointing outside all fail. File contents reach a
  third-party LLM API, so an unconstrained path would be an arbitrary-read
  and exfiltration primitive.
- **Read-only, and allowlisted.** Nothing writes to a checkout. Only known
  UI source extensions are read, which fails closed: `.env`, private
  keys, and anything else unanticipated are excluded by never being
  included, rather than by someone remembering to name them. Oversized
  and non-UTF-8 files are skipped too — a committed bundle is never where
  a human fixes a design bug, and it would swamp any prompt it reached.

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
