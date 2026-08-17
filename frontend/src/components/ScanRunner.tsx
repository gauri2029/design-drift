import { useState } from 'react'
import { MATCH_FIGMA_BREAKPOINT, STANDARD_BREAKPOINTS, type ScanMode } from '../lib/api'

interface ScanRunnerProps {
  onRun: (mode: ScanMode) => Promise<void>
  onRunAllBreakpoints: () => Promise<void>
  running: boolean
}

export function ScanRunner({ onRun, onRunAllBreakpoints, running }: ScanRunnerProps) {
  // Match Figma is the recommended default for the baseline fidelity scan
  // (see MATCH_FIGMA_BREAKPOINT's docstring) — "Run all breakpoints" below
  // is unaffected, it always iterates only STANDARD_BREAKPOINTS.
  const [mode, setMode] = useState<ScanMode>(MATCH_FIGMA_BREAKPOINT)
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
        Scan mode
      </label>
      <select
        id="scan-breakpoint"
        value={mode}
        onChange={(event) => setMode(event.target.value as ScanMode)}
        disabled={running}
        className="rounded-md border border-slate-300 px-2 py-2 text-sm text-slate-900 shadow-sm transition focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
      >
        <option value={MATCH_FIGMA_BREAKPOINT}>Match Figma (recommended)</option>
        {STANDARD_BREAKPOINTS.map((name) => (
          <option key={name} value={name}>
            {name[0].toUpperCase() + name.slice(1)}
          </option>
        ))}
      </select>

      <button
        type="button"
        onClick={() => void run(() => onRun(mode))}
        disabled={running}
        className="rounded-md bg-gradient-to-br from-indigo-600 to-violet-600 px-4 py-2 text-sm font-medium text-white shadow-sm shadow-indigo-600/20 transition hover:from-indigo-500 hover:to-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
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
