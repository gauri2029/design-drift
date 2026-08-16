import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Review } from '../lib/api'
import { ReviewPanel } from './ReviewPanel'

const CREATED_REVIEW: Review = {
  id: 'review-1',
  scan_id: 'scan-1',
  model: 'claude-opus-5',
  result: {
    material_drift_detected: true,
    summary: 'The button is visibly narrower in production than in Figma.',
    findings: [
      {
        category: 'spacing',
        severity: 'major',
        title: 'Button is narrower than designed',
        description: 'Figma shows 200x100; production renders narrower.',
        evidence: 'The diff image highlights the button edge.',
        likely_area: 'the primary call-to-action button',
      },
    ],
  },
  created_at: '2026-01-02T00:00:00Z',
}

describe('ReviewPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('runs a review and shows the findings', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        const method = init?.method ?? 'GET'

        if (url.endsWith('/reviews') && method === 'GET') {
          return { ok: true, json: async () => [] }
        }
        if (url.endsWith('/reviews') && method === 'POST') {
          return { ok: true, json: async () => CREATED_REVIEW }
        }
        throw new Error(`Unexpected fetch: ${method} ${url}`)
      }),
    )

    render(<ReviewPanel projectId="proj-1" scanId="scan-1" />)

    expect(await screen.findByText(/no review yet/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /run ai review/i }))

    expect(await screen.findByText(/material drift detected/i)).toBeInTheDocument()
    expect(screen.getByText('Button is narrower than designed')).toBeInTheDocument()
    expect(screen.getByText(/likely area: the primary call-to-action button/i)).toBeInTheDocument()
  })

  it('surfaces an error from a failed review without crashing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        const method = init?.method ?? 'GET'

        if (url.endsWith('/reviews') && method === 'GET') {
          return { ok: true, json: async () => [] }
        }
        if (url.endsWith('/reviews') && method === 'POST') {
          return {
            ok: false,
            status: 502,
            json: async () => ({ detail: 'ANTHROPIC_API_KEY is not configured' }),
          }
        }
        throw new Error(`Unexpected fetch: ${method} ${url}`)
      }),
    )

    render(<ReviewPanel projectId="proj-1" scanId="scan-1" />)
    await screen.findByText(/no review yet/i)

    fireEvent.click(screen.getByRole('button', { name: /run ai review/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('ANTHROPIC_API_KEY is not configured')
  })
})
