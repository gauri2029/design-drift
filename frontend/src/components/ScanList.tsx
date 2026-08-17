import type { Scan } from '../lib/api'
import { Badge } from './Badge'

interface ScanListProps {
  scans: Scan[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function ScanList({ scans, selectedId, onSelect }: ScanListProps) {
  if (scans.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
        No scans yet — run one to compare against the target app.
      </p>
    )
  }

  return (
    <ul className="space-y-1.5">
      {scans.map((scan) => {
        const isSelected = scan.id === selectedId
        return (
          <li key={scan.id}>
            <button
              type="button"
              onClick={() => onSelect(scan.id)}
              aria-current={isSelected}
              className={`flex w-full items-start gap-2 rounded-md border-l-2 px-3 py-2 text-left text-sm transition ${
                isSelected
                  ? 'border-indigo-500 bg-indigo-50 text-slate-900 dark:bg-indigo-950/40 dark:text-slate-100'
                  : 'border-transparent text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              <span
                className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${mismatchDotClass(scan.comparison_result.mismatch_percentage)}`}
                aria-hidden="true"
              />
              <span className="min-w-0">
                <span className="block font-medium">
                  {new Date(scan.created_at).toLocaleString()}
                  {scan.breakpoint && (
                    <Badge tone="neutral" className="ml-2 font-normal">
                      {scan.breakpoint}
                    </Badge>
                  )}
                </span>
                <span className="block text-xs text-slate-500 dark:text-slate-500">
                  {scan.comparison_result.mismatch_percentage.toFixed(2)}% pixel mismatch ·{' '}
                  {scan.accessibility_report.violation_count} a11y{' '}
                  {scan.accessibility_report.violation_count === 1 ? 'issue' : 'issues'}
                </span>
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

function mismatchDotClass(mismatchPercentage: number): string {
  if (mismatchPercentage === 0) return 'bg-emerald-500'
  if (mismatchPercentage < 5) return 'bg-amber-500'
  return 'bg-red-500'
}
