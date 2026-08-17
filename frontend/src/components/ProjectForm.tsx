import { useState, type ChangeEvent, type FormEvent } from 'react'
import type { ProjectCreateInput } from '../lib/api'

interface ProjectFormProps {
  onCreate: (input: ProjectCreateInput) => Promise<void>
  submitting: boolean
}

const emptyForm: ProjectCreateInput = {
  name: '',
  figma_file_key: '',
  figma_node_id: '',
  target_url: '',
  target_selector: '',
}

export function ProjectForm({ onCreate, submitting }: ProjectFormProps) {
  const [form, setForm] = useState<ProjectCreateInput>(emptyForm)
  const [formError, setFormError] = useState<string | null>(null)

  const handleChange =
    (field: keyof ProjectCreateInput) => (event: ChangeEvent<HTMLInputElement>) => {
      setForm((current) => ({ ...current, [field]: event.target.value }))
    }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setFormError(null)
    try {
      const trimmedSelector = form.target_selector?.trim()
      await onCreate({ ...form, target_selector: trimmedSelector || undefined })
      setForm(emptyForm)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to create project')
    }
  }

  return (
    <form
      onSubmit={(event) => void handleSubmit(event)}
      className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <div>
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          Register a project
        </h2>
        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-500">
          A Figma node paired with the app URL that should implement it.
        </p>
      </div>

      <Field label="Name" value={form.name} onChange={handleChange('name')} placeholder="Marketing homepage" />
      <Field
        label="Figma file key"
        value={form.figma_file_key}
        onChange={handleChange('figma_file_key')}
        placeholder="AbC123XyZ"
      />
      <Field
        label="Figma node id"
        value={form.figma_node_id}
        onChange={handleChange('figma_node_id')}
        placeholder="1:23"
      />
      <Field
        label="Target app URL"
        value={form.target_url}
        onChange={handleChange('target_url')}
        placeholder="http://localhost:3000"
        type="url"
      />
      <Field
        label="Target selector (optional)"
        value={form.target_selector ?? ''}
        onChange={handleChange('target_selector')}
        placeholder="#hero-cta"
        required={false}
      />

      {formError && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {formError}
        </p>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-md bg-gradient-to-br from-indigo-600 to-violet-600 px-4 py-2 text-sm font-medium text-white shadow-sm shadow-indigo-600/20 transition hover:from-indigo-500 hover:to-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {submitting ? 'Fetching from Figma…' : 'Register project'}
      </button>
    </form>
  )
}

interface FieldProps {
  label: string
  value: string
  onChange: (event: ChangeEvent<HTMLInputElement>) => void
  placeholder?: string
  type?: string
  required?: boolean
}

function Field({ label, value, onChange, placeholder, type = 'text', required = true }: FieldProps) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-slate-700 dark:text-slate-300">{label}</span>
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        required={required}
        className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-slate-900 shadow-sm transition focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
      />
    </label>
  )
}
