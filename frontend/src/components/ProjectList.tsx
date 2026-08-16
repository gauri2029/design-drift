import type { Project } from '../lib/api'

interface ProjectListProps {
  projects: Project[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function ProjectList({ projects, selectedId, onSelect }: ProjectListProps) {
  if (projects.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
        No projects yet — register one to fetch its Figma design.
      </p>
    )
  }

  return (
    <ul className="space-y-1">
      {projects.map((project) => {
        const isSelected = project.id === selectedId
        return (
          <li key={project.id}>
            <button
              type="button"
              onClick={() => onSelect(project.id)}
              aria-current={isSelected}
              className={`w-full rounded-md px-3 py-2 text-left text-sm transition ${
                isSelected
                  ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                  : 'text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              <span className="block font-medium">{project.name}</span>
              <span className="block text-xs opacity-70">
                {project.figma_file_key} · {project.figma_node_id}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
