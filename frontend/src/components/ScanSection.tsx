import type { Project } from '../lib/api'
import { useScans } from '../hooks/useScans'
import { ScanDetail } from './ScanDetail'
import { ScanList } from './ScanList'
import { ScanRunner } from './ScanRunner'

interface ScanSectionProps {
  project: Project
}

export function ScanSection({ project }: ScanSectionProps) {
  const { scans, status, error, selectedScan, selectScan, running, runScan } = useScans(project.id)

  return (
    <section className="mt-8 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          Production comparison
        </h2>
        <ScanRunner onRun={runScan} running={running} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
        <div>
          {status === 'loading' && (
            <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>
          )}
          {status === 'error' && (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              {error}
            </p>
          )}
          {status === 'ready' && (
            <ScanList scans={scans} selectedId={selectedScan?.id ?? null} onSelect={selectScan} />
          )}
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <ScanDetail project={project} scan={selectedScan} />
        </div>
      </div>
    </section>
  )
}
