import { projectScreenshotUrl, scanDiffUrl, scanProductionUrl, type Project, type Scan } from '../lib/api'
import { Badge, type BadgeTone } from './Badge'
import { ReviewPanel } from './ReviewPanel'
import { ZoomableImage } from './ZoomableImage'

interface ScanDetailProps {
  project: Project
  scan: Scan | null
}

export function ScanDetail({ project, scan }: ScanDetailProps) {
  if (!scan) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-slate-300 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
        <span className="text-2xl" aria-hidden="true">
          🔍
        </span>
        Run a scan to compare the Figma design against the live app.
      </div>
    )
  }

  const result = scan.comparison_result

  return (
    <div className="space-y-6">
      <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
        Raw pixel mismatch from deterministic image diffing — not a design
        fidelity score or a categorized finding. Visual reasoning lands
        below, via the AI review.
      </div>

      <section>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Visual comparison
        </h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <ImagePanel label="Figma (expected)" src={projectScreenshotUrl(project.id)} />
          <ImagePanel label="Production (actual)" src={scanProductionUrl(project.id, scan.id)} />
          <ImagePanel label="Diff" src={scanDiffUrl(project.id, scan.id)} />
        </div>
      </section>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard label="Mismatch" value={`${result.mismatch_percentage.toFixed(2)}%`} />
        <StatCard
          label="Mismatched pixels"
          value={`${result.mismatched_pixels.toLocaleString()} / ${result.total_pixels.toLocaleString()}`}
        />
        <StatCard
          label="Dimensions match"
          value={result.dimensions_match ? 'Yes' : 'No — size differs'}
          emphasize={!result.dimensions_match}
        />
        <StatCard
          label="Figma size"
          value={`${result.expected_dimensions.width} × ${result.expected_dimensions.height}`}
        />
        <StatCard
          label="Production size"
          value={`${result.actual_dimensions.width} × ${result.actual_dimensions.height}`}
        />
        <StatCard
          label="Viewport"
          value={
            scan.breakpoint
              ? `${scan.viewport_width} × ${scan.viewport_height} (${scan.breakpoint})`
              : `${scan.viewport_width} × ${scan.viewport_height}`
          }
        />
      </dl>

      <AccessibilitySection report={scan.accessibility_report} />

      <ReviewPanel key={scan.id} projectId={project.id} scanId={scan.id} />

    </div>
  )
}

function AccessibilitySection({ report }: { report: Scan['accessibility_report'] }) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        Accessibility ({report.violation_count} {report.violation_count === 1 ? 'issue' : 'issues'}
        , via axe-core)
      </h3>
      {report.violations.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">No violations detected.</p>
      ) : (
        <ul className="space-y-2">
          {report.violations.map((violation) => (
            <li
              key={violation.id}
              className="rounded-md border border-slate-200 p-3 text-sm dark:border-slate-800"
            >
              <div className="flex items-center gap-2">
                <Badge tone={impactTone(violation.impact)}>{violation.impact ?? 'unknown'}</Badge>
                <span className="font-medium text-slate-900 dark:text-slate-100">
                  {violation.help}
                </span>
              </div>
              <p className="mt-1 text-slate-600 dark:text-slate-400">{violation.description}</p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
                {violation.nodes.length} element{violation.nodes.length === 1 ? '' : 's'} affected
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function impactTone(impact: string | null): BadgeTone {
  switch (impact) {
    case 'critical':
    case 'serious':
      return 'danger'
    case 'moderate':
      return 'warning'
    default:
      return 'neutral'
  }
}

function ImagePanel({ label, src }: { label: string; src: string }) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
        <ZoomableImage src={src} alt={label} />
      </div>
    </div>
  )
}

function StatCard({ label, value, emphasize }: { label: string; value: string; emphasize?: boolean }) {
  return (
    <div
      className={`rounded-lg border p-3 ${
        emphasize
          ? 'border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/40'
          : 'border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950'
      }`}
    >
      <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</dt>
      <dd
        className={`mt-0.5 truncate text-sm font-medium ${emphasize ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-slate-100'}`}
        title={value}
      >
        {value}
      </dd>
    </div>
  )
}
