import { projectScreenshotUrl, type Project } from '../lib/api'
import { useCursorLight } from '../lib/motion'
import { Thumb } from './ui'

/** The projects, as the frames you designed.
 *
 * The list this replaces showed `AbC123XyZ · 94:2143` under each name — the
 * Figma file key and node id, which identify a project to the API and to
 * nobody else. A thumbnail of the frame is what a person recognises, so that
 * is what the row leads with.
 */
export function ProjectList({
  projects,
  selectedId,
  onSelect,
}: {
  projects: Project[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  if (projects.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-edge px-3 py-6 text-center text-[13px] text-ink-faint">
        No projects yet.
      </p>
    )
  }

  return (
    <ul className="space-y-1.5">
      {projects.map((project, index) => (
        <ProjectRow
          key={project.id}
          project={project}
          index={index}
          selected={project.id === selectedId}
          onSelect={() => onSelect(project.id)}
        />
      ))}
    </ul>
  )
}

function ProjectRow({
  project,
  index,
  selected,
  onSelect,
}: {
  project: Project
  index: number
  selected: boolean
  onSelect: () => void
}) {
  const light = useCursorLight<HTMLButtonElement>()
  return (
    <li className="animate-rise" style={{ animationDelay: `${Math.min(index, 8) * 45}ms` }}>
      <button
        type="button"
        onClick={onSelect}
        onPointerMove={light.onPointerMove}
        aria-current={selected ? 'true' : undefined}
        className={`lit tilt group flex w-full items-center gap-3 rounded-2xl border p-2 text-left transition-colors duration-200 ${
          selected
            ? 'border-accent/40 bg-accent/10'
            : 'border-transparent text-ink-dim hover:border-edge hover:bg-tint'
        }`}
      >
        <Thumb
          src={projectScreenshotUrl(project.id)}
          alt={project.name}
          className="h-11 w-11 shrink-0 rounded-xl border border-edge"
        />
        <span className="min-w-0 flex-1">
          <span
            className={`block truncate text-[13px] font-medium ${
              selected ? 'text-ink' : 'text-ink-dim group-hover:text-ink'
            }`}
          >
            {project.name}
          </span>
          <span className="block truncate font-mono text-[11px] text-ink-faint">
            {hostOf(project.target_url)}
          </span>
        </span>
      </button>
    </li>
  )
}

/** The host alone. A full URL truncates to "https://exampl…" in a sidebar
 * this width, which identifies nothing. */
function hostOf(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return url
  }
}
