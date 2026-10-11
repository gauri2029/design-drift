import { useEffect, useState } from 'react'
import type { Project } from '../lib/api'
import { Button } from './ui'

/** Confirms deleting a project, which cannot be undone.
 *
 * Typing the name rather than a plain "Are you sure?": this removes every
 * run, screenshot and checkout the project ever produced, and a one-click
 * confirm next to a hover-revealed trash icon is exactly how someone
 * deletes months of work by accident (docs/principles.md #5).
 */
export function DeleteProjectDialog({
  project,
  onCancel,
  onConfirm,
}: {
  project: Project | null
  onCancel: () => void
  onConfirm: (project: Project) => Promise<void>
}) {
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!project) return
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onCancel()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [project, onCancel])

  if (!project) return null

  const confirmed = typed.trim() === project.name

  const remove = async () => {
    if (!confirmed) return
    setBusy(true)
    setError(null)
    try {
      await onConfirm(project)
      setTyped('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete that project')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-void/70 p-5 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-project-title"
    >
      <div className="animate-pop w-full max-w-md rounded-3xl border border-edge bg-raised p-6">
        <h2
          id="delete-project-title"
          className="font-display text-[19px] font-bold tracking-[-0.02em] text-ink"
        >
          Delete {project.name}?
        </h2>
        <p className="mt-2.5 text-[13px] leading-relaxed text-ink-dim">
          This removes the project, every scan and analysis it produced, their screenshots, and
          any cloned repository checkout. It can’t be undone.
        </p>
        <p className="mt-2 text-[13px] leading-relaxed text-ink-faint">
          Nothing is changed in your Figma file or your GitHub repository.
        </p>

        <label className="mt-5 block">
          <span className="mb-1.5 block text-[13px] text-ink-dim">
            Type <span className="font-medium text-ink">{project.name}</span> to confirm
          </span>
          <input
            autoFocus
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            className="w-full rounded-xl border border-edge-hi bg-tint px-3.5 py-2.5 text-sm text-ink transition-[border-color,box-shadow] duration-200 focus:border-bad focus:outline-none focus:ring-2 focus:ring-bad/25"
          />
        </label>

        {error && (
          <p role="alert" className="mt-3 text-[13px] text-bad">
            {error}
          </p>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button variant="danger" onClick={() => void remove()} disabled={!confirmed || busy}>
            {busy ? 'Deleting…' : 'Delete project'}
          </Button>
        </div>
      </div>
    </div>
  )
}
