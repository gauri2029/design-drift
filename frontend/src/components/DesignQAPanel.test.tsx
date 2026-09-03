import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DesignAnalysis, Project } from '../lib/api'
import { DesignQAPanel } from './DesignQAPanel'

const PROJECT: Project = {
  id: 'proj-1',
  name: 'Marketing homepage',
  figma_file_key: 'abc123',
  figma_node_id: '1:23',
  target_url: 'https://example.com',
  target_selector: '#hero-cta',
  source_path: 'marketing-site',
  figma_data: null,
  figma_screenshot_key: 'figma/proj-1/preview.png',
  figma_fetched_at: '2026-01-01T00:00:00Z',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const ANALYSIS: DesignAnalysis = {
  id: 'run-1',
  project_id: 'proj-1',
  model: 'gemini-2.5-flash',
  result: {
    layout_summary: 'A centered hero with one CTA.',
    design_intent: 'Drive signups.',
    key_components: [],
    implementation_risks: ['The heading spacing is easy to get wrong.'],
  },
  production_screenshot_key: 'design-analyses/run-1/production.png',
  comparison_result: null,
  diff_image_key: 'design-analyses/run-1/diff.png',
  visual_comparison: null,
  accessibility_report: null,
  accessibility_interpretation: null,
  aggregated_findings: {
    problems_found: true,
    findings: [
      {
        source: 'accessibility',
        priority: 'high',
        original_severity: 'high',
        title: 'color-contrast',
        detail: 'Low-vision users cannot read the button label.',
        likely_area: null,
      },
    ],
  },
  code_analysis: {
    summary: 'Findings map onto the button component.',
    locations: [
      {
        finding_title: 'color-contrast',
        no_match: false,
        location: {
          file_path: 'src/components/Button.tsx',
          line_start: 12,
          line_end: 14,
          code_evidence: '<button className="bg-slate-200 text-slate-300">',
        },
        explanation: 'This is where the low-contrast classes are applied.',
        confidence: 'high',
      },
    ],
  },
  fix_proposal: {
    summary: 'One patch raises the button contrast.',
    fixes: [
      {
        finding_title: 'color-contrast',
        no_fix: false,
        patch: {
          file_path: 'src/components/Button.tsx',
          line_start: 12,
          line_end: 12,
          original_code: '<button className="bg-slate-200 text-slate-300">',
          replacement_code: '<button className="bg-slate-900 text-white">',
        },
        explanation: 'Darkens the background so the label meets contrast requirements.',
        confidence: 'high',
        original_code_found: true,
      },
    ],
  },
  fix_review: null,
  created_at: '2026-01-02T00:00:00Z',
}

function stubFetch(handler: (url: string, method: string) => unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      return handler(url, init?.method ?? 'GET')
    }),
  )
}

describe('DesignQAPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('runs the workflow and shows findings with their source location', async () => {
    stubFetch((url, method) => {
      if (url.endsWith('/design-analysis') && method === 'GET') {
        return { ok: true, json: async () => [] }
      }
      if (url.endsWith('/design-analysis') && method === 'POST') {
        return { ok: true, json: async () => ANALYSIS }
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`)
    })

    render(<DesignQAPanel project={PROJECT} />)

    expect(await screen.findByText(/no workflow run yet/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /run design qa/i }))

    // Appears three times by design — the finding, the source location
    // found for it, and the patch proposed for it.
    expect(await screen.findAllByText('color-contrast')).toHaveLength(3)
    // The whole point of the code-analysis step: a real file and line.
    expect(screen.getByText('src/components/Button.tsx:12-14')).toBeInTheDocument()
    // Twice: as the located evidence, and as the code the patch replaces —
    // they're the same line, which is the point.
    expect(
      screen.getAllByText('<button className="bg-slate-200 text-slate-300">'),
    ).toHaveLength(2)
    expect(screen.getByText('<button className="bg-slate-900 text-white">')).toBeInTheDocument()
  })

  it('shows a proposed patch as before/after, flagging one that no longer applies', async () => {
    const stale = {
      ...ANALYSIS,
      fix_proposal: {
        summary: 'One patch.',
        fixes: [
          {
            ...ANALYSIS.fix_proposal!.fixes[0],
            finding_title: 'stale-patch',
            original_code_found: false,
          },
        ],
      },
    }
    stubFetch((url, method) => {
      if (url.endsWith('/design-analysis') && method === 'GET') {
        return { ok: true, json: async () => [stale] }
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`)
    })

    render(<DesignQAPanel project={PROJECT} />)

    expect(await screen.findByText('stale-patch')).toBeInTheDocument()
    expect(screen.getByText('<button className="bg-slate-900 text-white">')).toBeInTheDocument()
    // Ours, not the model's — a reviewer shouldn't find this out by
    // trying to apply the patch.
    expect(screen.getByText(/does not match current file/i)).toBeInTheDocument()
  })

  it('records an approve/reject decision on the proposed patches', async () => {
    const reviewed = {
      ...ANALYSIS,
      fix_review: {
        decisions: [{ finding_title: 'color-contrast', decision: 'approved' as const }],
        reviewed_at: '2026-01-03T00:00:00Z',
      },
    }
    const put = vi.fn()
    stubFetch((url, method) => {
      if (url.endsWith('/design-analysis') && method === 'GET') {
        return { ok: true, json: async () => [ANALYSIS] }
      }
      if (url.endsWith('/fix-review') && method === 'PUT') {
        put(url)
        return { ok: true, json: async () => reviewed }
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`)
    })

    render(<DesignQAPanel project={PROJECT} />)

    expect(await screen.findByText(/awaiting your review/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /approve/i }))
    fireEvent.click(screen.getByRole('button', { name: /save review/i }))

    expect(await screen.findByText(/reviewed /i)).toBeInTheDocument()
    expect(put).toHaveBeenCalledWith(
      expect.stringContaining('/design-analysis/run-1/fix-review'),
    )
    // The saved decision comes back from the server, not from local state.
    expect(screen.getByRole('button', { name: /update review/i })).toBeInTheDocument()
  })

  it('will not let a patch that does not apply be approved', async () => {
    stubFetch((url, method) => {
      if (url.endsWith('/design-analysis') && method === 'GET') {
        return {
          ok: true,
          json: async () => [
            {
              ...ANALYSIS,
              fix_proposal: {
                summary: 'One patch.',
                fixes: [{ ...ANALYSIS.fix_proposal!.fixes[0], original_code_found: false }],
              },
            },
          ],
        }
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`)
    })

    render(<DesignQAPanel project={PROJECT} />)

    // The backend refuses this too — this just keeps a reviewer from
    // spending a click to find out.
    expect(await screen.findByRole('button', { name: /approve/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /reject/i })).toBeEnabled()
  })

  it('surfaces a rejected review save without losing the decision', async () => {
    stubFetch((url, method) => {
      if (url.endsWith('/design-analysis') && method === 'GET') {
        return { ok: true, json: async () => [ANALYSIS] }
      }
      if (url.endsWith('/fix-review') && method === 'PUT') {
        return { ok: false, status: 409, json: async () => ({ detail: 'patch does not apply' }) }
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`)
    })

    render(<DesignQAPanel project={PROJECT} />)
    await screen.findByText(/awaiting your review/i)

    fireEvent.click(screen.getByRole('button', { name: /approve/i }))
    fireEvent.click(screen.getByRole('button', { name: /save review/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('patch does not apply')
    expect(screen.getByRole('button', { name: /approve/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('explains why code analysis is absent when no source checkout is configured', async () => {
    stubFetch((url, method) => {
      if (url.endsWith('/design-analysis') && method === 'GET') {
        return { ok: true, json: async () => [{ ...ANALYSIS, code_analysis: null }] }
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`)
    })

    render(<DesignQAPanel project={{ ...PROJECT, source_path: null }} />)

    expect(await screen.findByText(/no source checkout configured/i)).toBeInTheDocument()
  })

  it('reports a clean run when nothing material was found', async () => {
    stubFetch((url, method) => {
      if (url.endsWith('/design-analysis') && method === 'GET') {
        return {
          ok: true,
          json: async () => [
            {
              ...ANALYSIS,
              aggregated_findings: { problems_found: false, findings: [] },
              code_analysis: null,
            },
          ],
        }
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`)
    })

    render(<DesignQAPanel project={PROJECT} />)

    expect(await screen.findByText(/no material problems found/i)).toBeInTheDocument()
    // Code analysis is skipped because there was nothing to locate — a
    // different reason from "no checkout", and worth saying so.
    expect(screen.getByText(/no problems were found/i)).toBeInTheDocument()
  })

  it('surfaces a failed run without crashing', async () => {
    stubFetch((url, method) => {
      if (url.endsWith('/design-analysis') && method === 'GET') {
        return { ok: true, json: async () => [] }
      }
      if (url.endsWith('/design-analysis') && method === 'POST') {
        return {
          ok: false,
          status: 502,
          json: async () => ({ detail: 'GEMINI_API_KEY is not configured' }),
        }
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`)
    })

    render(<DesignQAPanel project={PROJECT} />)
    await screen.findByText(/no workflow run yet/i)

    fireEvent.click(screen.getByRole('button', { name: /run design qa/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('GEMINI_API_KEY is not configured')
  })
})
