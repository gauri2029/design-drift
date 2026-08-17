import { projectScreenshotUrl, type Project } from '../lib/api'
import { ZoomableImage } from './ZoomableImage'

interface FigmaPreviewProps {
  project: Project | null
}

export function FigmaPreview({ project }: FigmaPreviewProps) {
  if (!project) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-slate-300 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
        <span className="text-2xl" aria-hidden="true">
          🎨
        </span>
        Select or register a project to see its Figma preview.
      </div>
    )
  }

  const node = project.figma_data
  const box = node?.absoluteBoundingBox

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
        {project.figma_screenshot_key ? (
          <ZoomableImage
            src={projectScreenshotUrl(project.id)}
            alt={`Figma render of ${node?.name ?? project.name}`}
          />
        ) : (
          <div className="flex h-48 items-center justify-center text-sm text-slate-500 dark:text-slate-400">
            No screenshot fetched yet
          </div>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
        <Detail label="Node name" value={node?.name ?? '—'} />
        <Detail label="Node type" value={node?.type ?? '—'} />
        <Detail label="Layout mode" value={node?.layoutMode ?? '—'} />
        <Detail label="Size" value={box ? `${Math.round(box.width)} × ${Math.round(box.height)}` : '—'} />
        <Detail label="Target app" value={project.target_url} />
        <Detail
          label="Fetched"
          value={project.figma_fetched_at ? new Date(project.figma_fetched_at).toLocaleString() : '—'}
        />
      </dl>
    </div>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="truncate text-slate-900 dark:text-slate-100" title={value}>
        {value}
      </dd>
    </div>
  )
}
