import type { Scan } from '../lib/api'

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
    <ul className="space-y-1">
      {scans.map((scan) => {
        const isSelected = scan.id === selectedId
        return (
          <li key={scan.id}>
            <button
              type="button"
              onClick={() => onSelect(scan.id)}
              aria-current={isSelected}
              className={`w-full rounded-md px-3 py-2 text-left text-sm transition ${
                isSelected
                  ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                  : 'text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              <span className="block font-medium">{new Date(scan.created_at).toLocaleString()}</span>
              <span className="block text-xs opacity-70">
                {scan.comparison_result.mismatch_percentage.toFixed(2)}% pixel mismatch
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
