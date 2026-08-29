import { useProjects } from '../hooks/useProjects'
import { DesignQAPanel } from './DesignQAPanel'
import { FigmaPreview } from './FigmaPreview'
import { ProjectForm } from './ProjectForm'
import { ProjectList } from './ProjectList'
import { ScanSection } from './ScanSection'

export function ProjectsPanel() {
  const { projects, status, error, selectedProject, selectProject, submitting, createProject } =
    useProjects()

  return (
    <div>
      <section className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <div className="space-y-6">
          <ProjectForm onCreate={createProject} submitting={submitting} />

          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <h2 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
              Projects
            </h2>
            {status === 'loading' && (
              <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>
            )}
            {status === 'error' && (
              <p role="alert" className="text-sm text-red-600 dark:text-red-400">
                {error}
              </p>
            )}
            {status === 'ready' && (
              <ProjectList
                projects={projects}
                selectedId={selectedProject?.id ?? null}
                onSelect={selectProject}
              />
            )}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-slate-100">
            Figma preview
          </h2>
          <FigmaPreview project={selectedProject} />
        </div>
      </section>

      {/* key forces a remount on project switch, so useScans' own initial
          state naturally resets instead of the hook resetting `status`
          itself inside an effect. */}
      {selectedProject && (
        <>
          <DesignQAPanel key={`qa-${selectedProject.id}`} project={selectedProject} />
          <ScanSection key={selectedProject.id} project={selectedProject} />
        </>
      )}
    </div>
  )
}
