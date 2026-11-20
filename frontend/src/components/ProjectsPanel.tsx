import { useState } from 'react'
import { useProjects } from '../hooks/useProjects'
import type { Project } from '../lib/api'
import { DemoNotice } from './DemoNotice'
import { NewProjectDialog } from './NewProjectDialog'
import { DeleteProjectDialog } from './DeleteProjectDialog'
import { ProjectList } from './ProjectList'
import { Workspace } from './Workspace'
import { Button, EmptyState, Label } from './ui'

/** A rail of projects beside the workspace for the selected one.
 *
 * Replaces a stacked page where the registration form, the project list, the
 * Figma preview, the QA report and the scan tool were all peers of each
 * other. Here choosing a project is navigation; everything else is the work.
 */
export function ProjectsPanel({
  demoLocked = false,
  demoOwnerName = null,
}: {
  /** True when an anonymous visitor is browsing the public showcase.
   *
   * Hides the controls that need an account and disables the ones the API
   * would refuse, so the boundary is visible before a click rather than
   * after it. The API enforces it either way - this is presentation, not
   * the permission (see app/services/demo.py). */
  demoLocked?: boolean
  demoOwnerName?: string | null
} = {}) {
  const {
    projects,
    status,
    error,
    selectedProject,
    selectProject,
    submitting,
    createProject,
    deleteProject,
  } = useProjects()
  const [pendingDelete, setPendingDelete] = useState<Project | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)

  return (
    <>
      {demoLocked && <DemoNotice ownerName={demoOwnerName} />}

      <div className="grid gap-6 lg:grid-cols-[244px_1fr]">
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="mb-3 flex items-center justify-between gap-2 px-1">
            <Label>Projects</Label>
            {/* Creating a project needs an account, so the demo has no use
                for this button at all. */}
            {!demoLocked && (
              <Button size="sm" variant="ghost" onClick={() => setDialogOpen(true)}>
                + New
              </Button>
            )}
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
              // Under the demo lock the row's delete control is not
              // rendered, so this is never reached. Kept as a function
              // rather than made optional because every other caller wants
              // it, and an optional prop would let a real caller forget it.
              canDelete={!demoLocked}
              onDelete={setPendingDelete}
            />
          )}
        </aside>

        <div id="workspace" className="min-w-0">
          {selectedProject ? (
            /* Remounted per project so the analyses hook starts clean rather
               than resetting itself inside an effect. */
            <Workspace
              key={selectedProject.id}
              project={selectedProject}
              demoLocked={demoLocked}
            />
          ) : (
            <EmptyState
              title={demoLocked ? 'Pick the demo project' : 'Point this at a design'}
              body={
                demoLocked
                  ? 'Open the project on the left to read a real agent run: what drifted from the design, where in the source it came from, and the patch that fixed it.'
                  : "Give it a link to a Figma frame and the page that should match it, and it will tell you where they've drifted apart."
              }
              action={
                demoLocked ? undefined : (
                  <Button variant="primary" size="lg" onClick={() => setDialogOpen(true)}>
                    New project
                  </Button>
                )
              }
            />
          )}
        </div>
      </div>

      <NewProjectDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreate={createProject}
        submitting={submitting}
      />

      <DeleteProjectDialog
        project={pendingDelete}
        onCancel={() => setPendingDelete(null)}
        onConfirm={async (project) => {
          await deleteProject(project.id)
          setPendingDelete(null)
        }}
      />
    </>
  )
}
