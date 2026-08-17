import { Badge } from './Badge'

const PLANNED_AGENTS = ['Design Analysis', 'Production Analysis', 'Visual Comparison', 'Fix Agent']

// Placeholder for the LangGraph agent workflow (Phase 3+, see
// docs/architecture.md). Deliberately static — no fake findings/timeline
// data — this just reserves and previews the layout the real structured
// findings will populate.
export function AgentActivityPanel() {
  return (
    <div className="mt-4 rounded-lg border border-dashed border-indigo-300 bg-indigo-50/40 p-5 dark:border-indigo-900 dark:bg-indigo-950/20">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-medium uppercase tracking-wide text-indigo-700 dark:text-indigo-300">
          Agent activity
        </h3>
        <Badge tone="info">Coming in Phase 3</Badge>
      </div>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
        Structured, multi-agent findings will populate here — reasoning over this scan and
        proposing patches for human review, instead of the raw pixel-diff and axe-core output
        above.
      </p>
      <ul className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {PLANNED_AGENTS.map((name) => (
          <li
            key={name}
            className="rounded-md border border-slate-200 bg-white px-2 py-1.5 text-center text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400"
          >
            {name}
          </li>
        ))}
      </ul>
    </div>
  )
}
