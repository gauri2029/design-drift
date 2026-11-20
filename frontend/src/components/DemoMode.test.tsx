/** How the app presents the public demo.
 *
 * The API is what enforces the read-only rule (backend
 * tests/test_demo_mode.py drives that, including by mutation). These tests
 * are about the other half: that an anonymous visitor on a demo deployment
 * reaches the workspace at all, is told plainly what is real, and is not
 * offered controls that would be refused.
 *
 * The honesty of the labelling is the part worth locking down. A demo that
 * showed stored results while implying they were live would be exactly the
 * thing docs/principles.md #2 rules out, and it would be an easy regression
 * to introduce by deleting one component.
 */

import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

const PROJECT = {
  id: 'project-1',
  name: 'Recipes Gallery',
  figma_file_key: 'k',
  figma_node_id: '1:2',
  target_url: 'https://recipes-gallery.example.com',
  target_selector: null,
  source_path: null,
  github_repo_full_name: 'gauri2029/recipes-gallery',
  github_branch: 'main',
  figma_data: null,
  figma_screenshot_key: null,
  figma_fetched_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

/** A deployment serving the showcase, seen by someone with no token. */
function stubDemoDeployment({ seeded = true }: { seeded?: boolean } = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.includes('/demo/status')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            enabled: true,
            seeded,
            user_name: seeded ? 'Design Drift Demo' : null,
          }),
        }
      }
      if (url.includes('/auth/me')) return { ok: false, status: 401, json: async () => ({}) }
      if (url.includes('/projects') && !url.includes('design-analysis')) {
        return { ok: true, status: 200, json: async () => [PROJECT] }
      }
      return { ok: true, status: 200, json: async () => [] }
    }),
  )
}

describe('the public demo', () => {
  beforeEach(() => {
    localStorage.clear()
    window.history.pushState(null, '', '/app')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('lets a visitor with no token reach the workspace', async () => {
    stubDemoDeployment()
    render(<App />)

    // The whole point: no signup wall in front of the demo.
    expect(await screen.findByText('Projects')).toBeInTheDocument()
    // The heading, not just any mention: the name also appears in the
    // project rail, and what matters is that the workspace itself opened.
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Recipes Gallery' }),
    ).toBeInTheDocument()
  })

  it('says the results are from a real run and that new runs are off', async () => {
    stubDemoDeployment()
    render(<App />)

    const notice = await screen.findByRole('region', { name: /real agent run/i })
    // Both halves have to be present. Either alone is a misleading demo:
    // "real" without "locked" oversells it, "locked" without "real" sells
    // it short.
    expect(notice).toHaveTextContent(/produced by the agents/i)
    expect(notice).toHaveTextContent(/Nothing here is mocked/i)
    expect(notice).toHaveTextContent(/turned off is starting a/i)
  })

  it('offers a way in instead of an account menu', async () => {
    stubDemoDeployment()
    render(<App />)

    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try it' })).toBeInTheDocument()
    // Nothing to open: there is no account.
    expect(screen.queryByRole('button', { name: /account/i })).not.toBeInTheDocument()
  })

  it('does not offer the controls the API would refuse', async () => {
    stubDemoDeployment()
    render(<App />)

    await screen.findByRole('heading', { level: 1, name: 'Recipes Gallery' })

    // Creating a project needs an account, so the control is absent rather
    // than disabled.
    expect(screen.queryByRole('button', { name: '+ New' })).not.toBeInTheDocument()
  })

  it('falls back to the landing page when the demo is not seeded', async () => {
    // A deployment switched on before its seed has run must not promise a
    // demo that is not there.
    stubDemoDeployment({ seeded: false })
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/drifted/i)
    })
    expect(screen.queryByText('Projects')).not.toBeInTheDocument()
  })

  it('shows the landing page on a deployment that is not a demo', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString()
        if (url.includes('/demo/status')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ enabled: false, seeded: false, user_name: null }),
          }
        }
        return { ok: false, status: 401, json: async () => ({}) }
      }),
    )
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/drifted/i)
    })
  })

  it('still works when /demo/status cannot be reached', async () => {
    // A backend that is down must leave the landing page renderable, not
    // throw on load.
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new Error('offline'))))
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/drifted/i)
    })
  })
})
