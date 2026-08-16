import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Project, Scan } from '../lib/api'
import { ScanSection } from './ScanSection'

const PROJECT: Project = {
  id: 'proj-1',
  name: 'Marketing homepage',
  figma_file_key: 'abc123',
  figma_node_id: '1:23',
  target_url: 'https://example.com',
  target_selector: '#hero-cta',
  figma_data: null,
  figma_screenshot_key: 'figma/proj-1/preview.png',
  figma_fetched_at: '2026-01-01T00:00:00Z',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const CREATED_SCAN: Scan = {
  id: 'scan-1',
  project_id: 'proj-1',
  viewport_width: 1280,
  viewport_height: 800,
  breakpoint: null,
  production_screenshot_key: 'scans/scan-1/production.png',
  diff_image_key: 'scans/scan-1/diff.png',
  comparison_result: {
    expected_dimensions: { width: 200, height: 100 },
    actual_dimensions: { width: 200, height: 100 },
    dimensions_match: true,
    compared_dimensions: { width: 200, height: 100 },
    mismatched_pixels: 40,
    total_pixels: 20000,
    mismatch_percentage: 0.2,
  },
  accessibility_report: { violations: [], violation_count: 0 },
  created_at: '2026-01-02T00:00:00Z',
}

describe('ScanSection', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('runs a scan and shows the comparison detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        const method = init?.method ?? 'GET'

        if (url.endsWith('/scans') && method === 'GET') {
          return { ok: true, json: async () => [] }
        }
        if (url.endsWith('/reviews') && method === 'GET') {
          return { ok: true, json: async () => [] }
        }
        if (url.endsWith('/scans') && method === 'POST') {
          return { ok: true, json: async () => CREATED_SCAN }
        }
        throw new Error(`Unexpected fetch: ${method} ${url}`)
      }),
    )

    render(<ScanSection project={PROJECT} />)

    expect(await screen.findByText(/no scans yet/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /run scan/i }))

    expect(await screen.findByText(/0\.20% pixel mismatch/i)).toBeInTheDocument()
    expect(screen.getByText('0.20%')).toBeInTheDocument()
    expect(screen.getByText('Yes')).toBeInTheDocument() // dimensions match

    expect(screen.getByRole('img', { name: /figma \(expected\)/i })).toHaveAttribute(
      'src',
      expect.stringContaining('/api/v1/projects/proj-1/figma/screenshot'),
    )
    expect(screen.getByRole('img', { name: /production \(actual\)/i })).toHaveAttribute(
      'src',
      expect.stringContaining('/api/v1/projects/proj-1/scans/scan-1/production'),
    )
    expect(screen.getByRole('img', { name: /^diff$/i })).toHaveAttribute(
      'src',
      expect.stringContaining('/api/v1/projects/proj-1/scans/scan-1/diff'),
    )
  })

  it('surfaces a 502-style error from a failed scan without crashing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        const method = init?.method ?? 'GET'

        if (url.endsWith('/scans') && method === 'GET') {
          return { ok: true, json: async () => [] }
        }
        if (url.endsWith('/reviews') && method === 'GET') {
          return { ok: true, json: async () => [] }
        }
        if (url.endsWith('/scans') && method === 'POST') {
          return { ok: false, status: 502, json: async () => ({ detail: 'selector not found' }) }
        }
        throw new Error(`Unexpected fetch: ${method} ${url}`)
      }),
    )

    render(<ScanSection project={PROJECT} />)
    await screen.findByText(/no scans yet/i)

    fireEvent.click(screen.getByRole('button', { name: /run scan/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('selector not found')
  })
})
