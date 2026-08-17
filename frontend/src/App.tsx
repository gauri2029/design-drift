import { HealthStatus } from './components/HealthStatus'
import { ProjectsPanel } from './components/ProjectsPanel'

function App() {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/80 backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/80">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-6 py-4">
          <div className="flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-sm font-bold text-white shadow-sm shadow-indigo-500/30"
            >
              DD
            </span>
            <span className="whitespace-nowrap text-base font-semibold tracking-tight text-slate-900 dark:text-slate-100">
              Design Drift
            </span>
          </div>
          <HealthStatus />
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-10">
        <div className="max-w-2xl">
          <span className="inline-flex items-center rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:border-indigo-900 dark:bg-indigo-950 dark:text-indigo-300">
            Design QA
          </span>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            Autonomous AI Design QA &amp; Remediation
          </h1>
          <p className="mt-2 text-slate-600 dark:text-slate-400">
            Register a Figma node and a target app URL to pixel-diff, accessibility-scan, and
            AI-review production against its design — with autonomous agent remediation landing
            next.
          </p>
        </div>

        <div className="mt-8">
          <ProjectsPanel />
        </div>
      </main>
    </div>
  )
}

export default App
