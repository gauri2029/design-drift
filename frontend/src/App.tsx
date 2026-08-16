import { HealthStatus } from './components/HealthStatus'
import { ProjectsPanel } from './components/ProjectsPanel'

function App() {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <span className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Design Drift
          </span>
          <HealthStatus />
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-10">
        <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
          Autonomous AI Design QA &amp; Remediation
        </h1>
        <p className="mt-2 max-w-xl text-slate-600 dark:text-slate-400">
          Phase 1: register a project (a Figma node + a target app URL) and
          fetch its design data. Production comparison and the agent
          workflow land in later phases.
        </p>

        <div className="mt-8">
          <ProjectsPanel />
        </div>
      </main>
    </div>
  )
}

export default App
