import { useState } from 'react'

interface ScanRunnerProps {
  onRun: () => Promise<void>
  running: boolean
}

export function ScanRunner({ onRun, running }: ScanRunnerProps) {
  const [error, setError] = useState<string | null>(null)

  const handleClick = async () => {
    setError(null)
    try {
      await onRun()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run scan')
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={() => void handleClick()}
        disabled={running}
        className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
      >
        {running ? 'Running scan…' : 'Run scan'}
      </button>
      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  )
}
