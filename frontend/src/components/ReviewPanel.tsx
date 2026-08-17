import { useState } from 'react'
import type { DesignFinding } from '../lib/api'
import { useReviews } from '../hooks/useReviews'
import { Badge, type BadgeTone } from './Badge'

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
          className="rounded-md border border-indigo-300 px-3 py-1.5 text-sm font-medium text-indigo-700 transition hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-indigo-800 dark:text-indigo-300 dark:hover:bg-indigo-950/40"
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
        <Badge tone={severityTone(finding.severity)}>{finding.severity}</Badge>
        <Badge tone="neutral">{finding.category}</Badge>
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

function severityTone(severity: DesignFinding['severity']): BadgeTone {
  switch (severity) {
    case 'critical':
      return 'danger'
    case 'major':
      return 'orange'
    case 'minor':
      return 'warning'
    default:
      return 'neutral'
  }
}
