# Design Drift — Frontend

React + TypeScript (strict) + Vite + Tailwind CSS v4.

## Setup

```bash
cd frontend
npm install
```

The API base URL defaults to `http://localhost:8000` (see
`src/lib/api.ts`). To point at a different backend, create
`frontend/.env.local` with `VITE_API_BASE_URL=...`.

## Run

```bash
npm run dev
```

Open http://localhost:5173 — the header shows live backend connectivity
(calls `GET /api/v1/health` on the FastAPI backend).

## Test / lint / typecheck

```bash
npm run test
npm run lint
npm run typecheck
```

## Layout

- `src/components/` — UI components (dashboard, comparison views, overlays
  — grows through later phases).
- `src/lib/` — API client and other framework-agnostic helpers.
- `src/test/setup.ts` — Vitest + Testing Library setup.
