import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Project } from '../lib/api'
import { ProjectsPanel } from './ProjectsPanel'

const CREATED_PROJECT: Project = {
  id: 'proj-1',
  name: 'Marketing homepage',
  figma_file_key: 'abc123',
  figma_node_id: '1:23',
  target_url: 'https://example.com',
  target_selector: null,
  figma_data: {
    id: '1:23',
    name: 'Button',
    type: 'FRAME',
    visible: true,
    absoluteBoundingBox: { x: 0, y: 0, width: 120, height: 40 },
    layoutMode: 'HORIZONTAL',
    children: [],
  },
  figma_screenshot_key: 'figma/proj-1/preview.png',
  figma_fetched_at: '2026-01-01T00:00:00Z',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

describe('ProjectsPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('registers a project and shows its Figma preview', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        const method = init?.method ?? 'GET'

        if (url.endsWith('/api/v1/projects') && method === 'GET') {
          return { ok: true, json: async () => [] }
        }
        if (url.endsWith('/api/v1/projects') && method === 'POST') {
          return { ok: true, json: async () => CREATED_PROJECT }
        }
        if (url.endsWith('/scans') && method === 'GET') {
          return { ok: true, json: async () => [] }
        }
        throw new Error(`Unexpected fetch: ${method} ${url}`)
      }),
    )

    render(<ProjectsPanel />)

    expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: 'Marketing homepage' } })
    fireEvent.change(screen.getByLabelText(/figma file key/i), { target: { value: 'abc123' } })
    fireEvent.change(screen.getByLabelText(/figma node id/i), { target: { value: '1:23' } })
    fireEvent.change(screen.getByLabelText(/target app url/i), {
      target: { value: 'https://example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /register project/i }))

    expect(await screen.findByRole('button', { name: /marketing homepage/i })).toBeInTheDocument()
    expect(screen.getByText('Button')).toBeInTheDocument()

    const image = screen.getByRole('img', { name: /figma render of button/i })
    expect(image.getAttribute('src')).toContain('/api/v1/projects/proj-1/figma/screenshot')

    expect(await screen.findByRole('button', { name: /run scan/i })).toBeInTheDocument()
    expect(await screen.findByText(/no scans yet/i)).toBeInTheDocument()
  })

  it('shows the backend list error when loading projects fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }),
    )

    render(<ProjectsPanel />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/failed to list projects/i)
  })
})
