import { useEffect, useRef, useState, type FormEvent } from 'react'
import type { ProjectCreateInput } from '../lib/api'
import { parseFigmaUrl } from '../lib/figmaUrl'
import { Button, Chevron, Label } from './ui'

/** Creating a project, as a dialog and as three questions.
 *
 * The form this replaces asked for six fields, two of which — "Figma file
 * key" and "Figma node id" — required reading a URL and retyping two
 * substrings of it. Both are already in the link Figma hands you, so this
 * takes the link and shows what it understood, which turns a wrong paste
 * into an immediate "couldn't read that" rather than a 404 three steps on.
 *
 * It is a dialog because registering is a once-per-project act; reviewing
 * drift is what you come back for. A permanent form owning the top of the
 * page had that weighting backwards.
 */
export function NewProjectDialog({
  open,
  onClose,
  onCreate,
  submitting,
}: {
  open: boolean
  onClose: () => void
  onCreate: (input: ProjectCreateInput) => Promise<void>
  submitting: boolean
}) {
  const [name, setName] = useState('')
  const [figmaUrl, setFigmaUrl] = useState('')
  const [targetUrl, setTargetUrl] = useState('')
  const [sourcePath, setSourcePath] = useState('')
  const [selector, setSelector] = useState('')
  const [advanced, setAdvanced] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const firstField = useRef<HTMLInputElement>(null)

  const parsed = figmaUrl.trim() ? parseFigmaUrl(figmaUrl) : null

  useEffect(() => {
    if (open) firstField.current?.focus()
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!parsed) {
      setError('That doesn’t look like a link to a Figma frame. Copy the link to a selected frame.')
      return
    }
    try {
      await onCreate({
        name,
        figma_file_key: parsed.fileKey,
        figma_node_id: parsed.nodeId,
        target_url: targetUrl,
        // Empty optional fields are omitted rather than sent as "": the
        // backend reads null as "not configured", and "" would resolve to
        // the source root itself.
        target_selector: selector.trim() || undefined,
        source_path: sourcePath.trim() || undefined,
      })
      onClose()
      setName('')
      setFigmaUrl('')
      setTargetUrl('')
      setSelector('')
      setSourcePath('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create that project')
    }
  }

  return (
    <div className="animate-fade fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-void/70 p-4 backdrop-blur-md sm:p-12">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-project-title"
        className="glass-deep animate-rise w-full max-w-lg rounded-3xl"
      >
        <div className="flex items-center justify-between border-b border-edge px-6 py-4">
          <h2 id="new-project-title" className="text-lg font-bold text-ink">
            New project
          </h2>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
            ✕
          </Button>
        </div>

        <form onSubmit={(event) => void submit(event)} className="space-y-5 p-6">
          <Field
            inputRef={firstField}
            label="What should we call it?"
            value={name}
            onChange={setName}
            placeholder="Marketing homepage"
            required
          />

          <div>
            <Field
              label="Link to the Figma frame"
              value={figmaUrl}
              onChange={setFigmaUrl}
              placeholder="https://figma.com/design/AbC123/Site?node-id=94-2143"
              required
              hint="In Figma: right-click a frame → Copy link to selection."
            />
            {figmaUrl.trim() && (
              <p className="animate-fade mt-2 font-mono text-xs">
                {parsed ? (
                  <span className="text-ok">
                    ✓ file {parsed.fileKey} · frame {parsed.nodeId}
                  </span>
                ) : (
                  <span className="text-warn">△ Couldn’t find a frame in that link</span>
                )}
              </p>
            )}
          </div>

          <Field
            label="The page it should match"
            value={targetUrl}
            onChange={setTargetUrl}
            placeholder="https://example.com/pricing"
            type="url"
            required
          />

          <div className="overflow-hidden rounded-2xl border border-edge">
            <button
              type="button"
              onClick={() => setAdvanced((current) => !current)}
              aria-expanded={advanced}
              className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm text-ink-dim transition-colors hover:bg-tint hover:text-ink"
            >
              <Chevron className={advanced ? 'rotate-90' : ''} />
              More options
              <span className="ml-auto text-[13px] text-ink-faint">optional</span>
            </button>
            {advanced && (
              <div className="animate-fade space-y-5 border-t border-edge p-4">
                <Field
                  label="Source folder"
                  value={sourcePath}
                  onChange={setSourcePath}
                  placeholder="marketing-site"
                  hint="A folder inside SOURCE_ROOT. Without it, issues can be found but not traced to code or fixed."
                />
                <Field
                  label="CSS selector"
                  value={selector}
                  onChange={setSelector}
                  placeholder="#hero"
                  hint="Compare one element instead of the whole page."
                />
              </div>
            )}
          </div>

          {error && (
            <p role="alert" className="text-sm text-bad">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={submitting}>
              {submitting ? 'Fetching from Figma…' : 'Create project'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  hint,
  type = 'text',
  required,
  inputRef,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  hint?: string
  type?: string
  required?: boolean
  inputRef?: React.RefObject<HTMLInputElement | null>
}) {
  return (
    <label className="block">
      <Label>{label}</Label>
      <input
        ref={inputRef}
        type={type}
        value={value}
        required={required}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="mt-2 w-full rounded-2xl border border-edge bg-void/50 px-4 py-2.5 text-sm text-ink transition-colors duration-200 placeholder:text-ink-faint/50 focus:border-accent/50 focus:bg-void/80"
      />
      {hint && <p className="mt-1.5 text-[13px] text-ink-faint">{hint}</p>}
    </label>
  )
}
