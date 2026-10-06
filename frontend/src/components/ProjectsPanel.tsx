import { useState } from 'react'
import { useProjects } from '../hooks/useProjects'
import { NewProjectDialog } from './NewProjectDialog'
import { ProjectList } from './ProjectList'
import { Workspace } from './Workspace'
import { Button, EmptyState, Label } from './ui'

/** A rail of projects beside the workspace for the selected one.
 *
 * Replaces a stacked page where the registration form, the project list, the
 * Figma preview, the QA report and the scan tool were all peers of each
 * other. Here choosing a project is navigation; everything else is the work.
 */
export function ProjectsPanel() {
  const { projects, status, error, selectedProject, selectProject, submitting, createProject } =
    useProjects()
  const [dialogOpen, setDialogOpen] = useState(false)

  return (
    <div className="grid gap-6 lg:grid-cols-[244px_1fr]">
      <aside className="lg:sticky lg:top-24 lg:self-start">
        <div className="mb-3 flex items-center justify-between gap-2 px-1">
          <Label>Projects</Label>
          <Button size="sm" variant="ghost" onClick={() => setDialogOpen(true)}>
            + New
          </Button>
        </div>

        {status === 'loading' && <p className="px-1 text-[13px] text-ink-faint">Loading…</p>}
        {status === 'error' && (
          <p role="alert" className="px-1 text-[13px] text-bad">
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
      </aside>

      <div id="workspace" className="min-w-0">
        {selectedProject ? (
          /* Remounted per project so the analyses hook starts clean rather
             than resetting itself inside an effect. */
          <Workspace key={selectedProject.id} project={selectedProject} />
        ) : (
          <EmptyState
            title="Point this at a design"
            body="Give it a link to a Figma frame and the page that should match it, and it will tell you where they've drifted apart."
            action={
              <Button variant="primary" size="lg" onClick={() => setDialogOpen(true)}>
                New project
              </Button>
            }
          />
        )}
      </div>

      <NewProjectDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreate={createProject}
        submitting={submitting}
      />
    </div>
  )
}
