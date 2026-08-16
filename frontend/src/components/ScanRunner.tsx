import { useState } from 'react'
import { STANDARD_BREAKPOINTS, type Breakpoint } from '../lib/api'

interface ScanRunnerProps {
  onRun: (breakpoint?: Breakpoint) => Promise<void>
  onRunAllBreakpoints: () => Promise<void>
  running: boolean
}

export function ScanRunner({ onRun, onRunAllBreakpoints, running }: ScanRunnerProps) {
  const [breakpoint, setBreakpoint] = useState<Breakpoint | ''>('')
  const [error, setError] = useState<string | null>(null)

  const run = async (action: () => Promise<void>) => {
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run scan')
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <label className="sr-only" htmlFor="scan-breakpoint">
        Breakpoint
      </label>
      <select
        id="scan-breakpoint"
        value={breakpoint}
        onChange={(event) => setBreakpoint(event.target.value as Breakpoint | '')}
        disabled={running}
        className="rounded-md border border-slate-300 px-2 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
      >
        <option value="">Default (1280 × 800)</option>
        {STANDARD_BREAKPOINTS.map((name) => (
          <option key={name} value={name}>
            {name[0].toUpperCase() + name.slice(1)}
          </option>
        ))}
      </select>

      <button
        type="button"
        onClick={() => void run(() => onRun(breakpoint || undefined))}
        disabled={running}
        className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
      >
        {running ? 'Running scan…' : 'Run scan'}
      </button>

      <button
        type="button"
        onClick={() => void run(onRunAllBreakpoints)}
        disabled={running}
        className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
      >
        Run all breakpoints
      </button>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  )
}
