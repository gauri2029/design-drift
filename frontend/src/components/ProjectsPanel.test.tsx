import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Project } from '../lib/api'
import { ProjectsPanel } from './ProjectsPanel'

const CREATED_PROJECT: Project = {
  id: 'proj-1',
  name: 'Marketing homepage',
  figma_file_key: '6vJNrp',
  figma_node_id: '94:2143',
  target_url: 'https://example.com',
  target_selector: null,
  source_path: null,
  github_repo_full_name: null,
  github_branch: null,
  figma_data: null,
  figma_screenshot_key: 'figma/proj-1/preview.png',
  figma_fetched_at: '2026-01-01T00:00:00Z',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

describe('ProjectsPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('creates a project from a Figma link, deriving the file key and node id', async () => {
    let posted: Record<string, unknown> | null = null
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        const method = init?.method ?? 'GET'
        if (url.endsWith('/api/v1/projects') && method === 'GET') {
          return { ok: true, json: async () => [] }
        }
        if (url.endsWith('/api/v1/projects') && method === 'POST') {
          posted = JSON.parse(String(init?.body))
          return { ok: true, json: async () => CREATED_PROJECT }
        }
        if (url.includes('/design-analysis')) return { ok: true, json: async () => [] }
        throw new Error(`Unexpected fetch: ${method} ${url}`)
      }),
    )

    render(<ProjectsPanel />)
    expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument()

    // Creation lives in a dialog: registering is a once-per-project act,
    // and a permanent six-field form owning the page had it backwards.
    fireEvent.click(screen.getByRole('button', { name: /\+ new/i }))
    const dialog = await screen.findByRole('dialog')

    fireEvent.change(screen.getByLabelText(/what should we call it/i), {
      target: { value: 'Marketing homepage' },
    })
    // One link instead of two fields the user would read out of it.
    fireEvent.change(screen.getByLabelText(/link to the figma frame/i), {
      target: { value: 'https://www.figma.com/design/6vJNrp/Site?node-id=94-2143' },
    })
    fireEvent.change(screen.getByLabelText(/the page it should match/i), {
      target: { value: 'https://example.com' },
    })

    // What it understood, before anything is submitted.
    expect(dialog).toHaveTextContent('6vJNrp')
    expect(dialog).toHaveTextContent('94:2143')

    fireEvent.click(screen.getByRole('button', { name: /create project/i }))

    expect(await screen.findByRole('button', { name: /marketing homepage/i })).toBeInTheDocument()
    expect(posted).toMatchObject({
      name: 'Marketing homepage',
      figma_file_key: '6vJNrp',
      figma_node_id: '94:2143',
      target_url: 'https://example.com',
    })
  })

  it('shows the backend list error when loading projects fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }),
    )

    render(<ProjectsPanel />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/failed to list projects/i)
  })

  it('deletes a project only after its name is typed', async () => {
    const calls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        const method = init?.method ?? 'GET'
        calls.push(`${method} ${url}`)
        if (url.endsWith('/api/v1/projects') && method === 'GET') {
          return { ok: true, json: async () => [CREATED_PROJECT] }
        }
        if (method === 'DELETE') return { ok: true, status: 204, json: async () => ({}) }
        return { ok: true, json: async () => [] }
      }),
    )

    render(<ProjectsPanel />)
    fireEvent.click(await screen.findByRole('button', { name: /delete this project/i }))

    const confirm = await screen.findByRole('button', { name: /delete project/i })
    // Guarded until the name matches: this removes every run and file the
    // project produced, and the trash icon sits one hover away from the row.
    expect(confirm).toBeDisabled()
    expect(calls.some((c) => c.startsWith('DELETE'))).toBe(false)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Marketing homepage' } })
    expect(confirm).not.toBeDisabled()
    fireEvent.click(confirm)

    await waitFor(() =>
      expect(calls.some((c) => c === `DELETE http://localhost:8000/api/v1/projects/proj-1`)).toBe(
        true,
      ),
    )
    // Gone from the rail, without a reload.
    expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument()
  })
})
