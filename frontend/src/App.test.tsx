import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const USER = {
  id: 'user-1',
  email: 'designer@example.com',
  name: 'Ada',
  created_at: '2026-01-01T00:00:00Z',
}

/** Answers the auth endpoints and leaves the workspace's own requests empty,
 * so these tests are about which screen renders, not about projects. */
function stubFetch(handlers: Record<string, () => unknown> = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      for (const [match, respond] of Object.entries(handlers)) {
        if (url.includes(match)) return respond()
      }
      if (url.includes('/auth/me')) return { ok: false, status: 401, json: async () => ({}) }
      return { ok: true, status: 200, json: async () => [] }
    }),
  )
}

function go(path: string) {
  window.history.pushState(null, '', path)
}

describe('App', () => {
  beforeEach(() => {
    localStorage.clear()
    go('/')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('shows the landing page to a visitor with no token', () => {
    stubFetch()
    render(<App />)

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/drifted/i)
    // The workspace must not be reachable without signing in.
    expect(screen.queryByText('Projects')).not.toBeInTheDocument()
  })

  it('does not call the API at all when there is no stored token', () => {
    stubFetch()
    render(<App />)

    // A landing-page visit shouldn't produce a 401 on every page load.
    expect(fetch).not.toHaveBeenCalled()
  })

  it('opens the signup form from Get started', () => {
    stubFetch()
    render(<App />)

    fireEvent.click(screen.getAllByRole('button', { name: 'Get started' })[0])

    expect(screen.getByRole('heading', { name: 'Create your account' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/signup')
  })

  it('renders the login form directly at /login', () => {
    stubFetch()
    go('/login')
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
    // Login asks for an email and a password, and not for a name.
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()
  })

  it('switches between login and signup without losing the screen', () => {
    stubFetch()
    go('/login')
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'Create one' }))
    expect(screen.getByLabelText('Name')).toBeInTheDocument()
    expect(window.location.pathname).toBe('/signup')
  })

  it('signing in lands on the existing workspace', async () => {
    stubFetch({
      '/auth/login': () => ({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'a-token', token_type: 'bearer', user: USER }),
      }),
    })
    go('/login')
    render(<App />)

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: USER.email } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'a password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    // The project rail is the existing dashboard — reaching it means the
    // pre-auth workflow is intact behind the login.
    expect(await screen.findByText('Projects')).toBeInTheDocument()
    expect(localStorage.getItem('design-drift.token')).toBe('a-token')
  })

  it('shows the API’s reason when sign-in fails, and stays on the form', async () => {
    stubFetch({
      '/auth/login': () => ({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'incorrect email or password' }),
      }),
    })
    go('/login')
    render(<App />)

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: USER.email } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('incorrect email or password')
    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
    // A failed attempt must re-enable the button rather than leave it spinning.
    expect(screen.getByRole('button', { name: 'Sign in' })).not.toBeDisabled()
  })

  it('reads a field-level 422 rather than rendering the raw array', async () => {
    stubFetch({
      '/auth/signup': () => ({
        ok: false,
        status: 422,
        json: async () => ({ detail: [{ msg: 'String should have at least 8 characters' }] }),
      }),
    })
    go('/signup')
    render(<App />)

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Ada' } })
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: USER.email } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'shortpw!' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('at least 8 characters')
    expect(alert).not.toHaveTextContent('object')
  })

  it('restores a session from a stored token', async () => {
    localStorage.setItem('design-drift.token', 'a-token')
    stubFetch({ '/auth/me': () => ({ ok: true, status: 200, json: async () => USER }) })
    go('/app')
    render(<App />)

    expect(await screen.findByText('Projects')).toBeInTheDocument()
  })

  it('falls back to the landing page when a stored token is rejected', async () => {
    localStorage.setItem('design-drift.token', 'expired')
    stubFetch()
    go('/app')
    render(<App />)

    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(/drifted/i)
    // The dead token is cleared, so the next load doesn't re-check it.
    await waitFor(() => expect(localStorage.getItem('design-drift.token')).toBeNull())
  })

  it('signing out clears the token and returns to the landing page', async () => {
    localStorage.setItem('design-drift.token', 'a-token')
    stubFetch({ '/auth/me': () => ({ ok: true, status: 200, json: async () => USER }) })
    go('/app')
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }))

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/drifted/i)
    expect(localStorage.getItem('design-drift.token')).toBeNull()
  })
})
