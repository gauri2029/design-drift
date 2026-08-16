import { useState } from 'react'
import type { DesignFinding } from '../lib/api'
import { useReviews } from '../hooks/useReviews'

interface ReviewPanelProps {
  projectId: string
  scanId: string
}

export function ReviewPanel({ projectId, scanId }: ReviewPanelProps) {
  const { latestReview, status, error, running, runReview } = useReviews(projectId, scanId)
  const [runError, setRunError] = useState<string | null>(null)

  const handleRun = async () => {
    setRunError(null)
    try {
      await runReview()
    } catch (err) {
      setRunError(err instanceof Error ? err.message : 'Failed to run AI review')
    }
  }

  return (
    <div className="mt-4 border-t border-slate-200 pt-4 dark:border-slate-800">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            AI visual review
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-500">
            One multimodal Claude call, judging the images above — not run automatically (costs
            real money per run).
          </p>
        </div>
        <button
          type="button"
          onClick={() => void handleRun()}
          disabled={running}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          {running ? 'Reviewing…' : 'Run AI review'}
        </button>
      </div>

      {runError && (
        <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">
          {runError}
        </p>
      )}

      {status === 'loading' && (
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Loading…</p>
      )}
      {status === 'error' && (
        <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      {status === 'ready' && !latestReview && (
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          No review yet for this scan.
        </p>
      )}

      {latestReview && (
        <div className="mt-3 space-y-3">
          <div
            className={`rounded-md border px-3 py-2 text-sm ${
              latestReview.result.material_drift_detected
                ? 'border-red-200 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300'
                : 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300'
            }`}
          >
            <span className="font-medium">
              {latestReview.result.material_drift_detected
                ? 'Material drift detected'
                : 'No material drift detected'}
            </span>{' '}
            — {latestReview.result.summary}
          </div>

          {latestReview.result.findings.length > 0 && (
            <ul className="space-y-2">
              {latestReview.result.findings.map((finding, index) => (
                <FindingItem key={index} finding={finding} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function FindingItem({ finding }: { finding: DesignFinding }) {
  return (
    <li className="rounded-md border border-slate-200 p-3 text-sm dark:border-slate-800">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${severityClasses(finding.severity)}`}
        >
          {finding.severity}
        </span>
        <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-700 dark:bg-slate-700 dark:text-slate-200">
          {finding.category}
        </span>
        <span className="font-medium text-slate-900 dark:text-slate-100">{finding.title}</span>
      </div>
      <p className="mt-1 text-slate-600 dark:text-slate-400">{finding.description}</p>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">Evidence: {finding.evidence}</p>
      {finding.likely_area && (
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
          Likely area: {finding.likely_area}
        </p>
      )}
    </li>
  )
}

function severityClasses(severity: DesignFinding['severity']): string {
  switch (severity) {
    case 'critical':
      return 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300'
    case 'major':
      return 'bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300'
    case 'minor':
      return 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300'
    default:
      return 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'
  }
}
