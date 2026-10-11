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
  onDelete,
}: {
  projects: Project[]
  selectedId: string | null
  onSelect: (id: string) => void
  onDelete: (project: Project) => void
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
          onDelete={() => onDelete(project)}
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
  onDelete,
}: {
  project: Project
  index: number
  selected: boolean
  onSelect: () => void
  onDelete: () => void
}) {
  const light = useCursorLight<HTMLButtonElement>()
  return (
    <li className="animate-rise" style={{ animationDelay: `${Math.min(index, 8) * 45}ms` }}>
      {/* The row and the delete control are siblings, not nested: a button
          inside a button is invalid HTML, and browsers resolve it by
          dropping one — which would make either the row or the delete
          unclickable. */}
      <div
        className={`lit tilt group relative flex w-full items-center rounded-2xl border transition-colors duration-200 ${
          selected
            ? 'border-accent/40 bg-accent/10'
            : 'border-transparent text-ink-dim hover:border-edge hover:bg-tint'
        }`}
      >
        <button
          type="button"
          onClick={onSelect}
          onPointerMove={light.onPointerMove}
          aria-current={selected ? 'true' : undefined}
          className="flex min-w-0 flex-1 items-center gap-3 p-2 text-left"
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

        {/* Appears on hover, and on keyboard focus — otherwise it would be
            reachable by tab but invisible to the person pressing tab. */}
        <button
          type="button"
          onClick={onDelete}
          // Deliberately not "Delete {name}": the row that opens the project
          // already announces that name, and two controls matching it make
          // "the Marketing homepage button" ambiguous to anyone navigating
          // by name. The dialog that opens names the project in full.
          aria-label={`Delete this project`}
          title={`Delete ${project.name}`}
          className="mr-2 grid h-7 w-7 shrink-0 place-items-center rounded-lg text-ink-faint opacity-0 transition-[opacity,color,background-color] duration-200 hover:bg-bad/10 hover:text-bad focus-visible:opacity-100 group-hover:opacity-100"
        >
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
            className="h-4 w-4"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          >
            <path d="M4 7h16M10 11v6M14 11v6M5 7l1 13h12l1-13M9 7V4h6v3" />
          </svg>
        </button>
      </div>
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
