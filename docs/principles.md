# Engineering principles

Ground rules this project follows, so decisions stay consistent as it grows.

## 1. Incremental, working software over big-bang design

Each phase ships something runnable and verifiable. We don't implement the
full target architecture in one pass — folders and abstractions
(`agents/`, `graph/`, `repositories/`, a vector store, Redis, ...) are added
when a phase actually needs them, not speculatively.

## 2. No fake AI

If a task has a deterministic answer, we compute it deterministically.
Playwright and DOM APIs answer "what are this element's dimensions,"
axe-core answers "which accessibility rules are violated," and image-diff
tooling answers "which pixels changed." The LLM is used for judgment: does
this pixel difference matter, what does this design intend, what's the
likely cause, what's a reasonable fix. Every AI architectural decision
should be defensible in an interview — "we used an LLM here because X
requires judgment, not because we could."

## 3. Understandable AI, not hidden behind frameworks

LangGraph nodes, edges, state, tool calls, and structured outputs stay
visible and readable — no wrapper abstractions that obscure the underlying
LLM calls, prompts, or routing logic. The person building this project is
learning AI engineering; the code has to teach, not just work.

## 4. Structured state between agents, not prose

Runtime agents communicate through a typed, shared LangGraph state object
(Pydantic models), not by handing each other paragraphs of natural language
to re-parse. Inputs, outputs, and failure behavior are explicit per agent.

## 5. Human control over consequential actions

The workflow pauses for human approval before applying a code fix or doing
anything hard to reverse. The application **never** creates, merges, or
pushes a GitHub pull request, and never pushes to a remote branch — the
repository owner handles all Git write operations manually.

## 6. Add technology only when there's a reason

Redis, a vector store, WebSockets, additional AWS services, extra agents —
each is introduced when a concrete requirement appears, with the reason
stated at the point it's added, not accumulated for their own sake.

## 7. Boring, typed, tested code beneath the AI layer

Type hints and Pydantic schemas throughout; `.env`-based config with a
committed `.env.example` and no real secrets in the repo; structured
logging; async I/O where it matters (I/O-bound agent/tool calls, DB
access); unit, integration, and API tests; linting and formatting enforced
in both backend (Ruff, mypy) and frontend (ESLint, TypeScript strict mode).
