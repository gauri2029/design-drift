import { useCallback, useEffect, useState } from 'react'
import {
  fetchCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  signup as signupRequest,
  readToken,
  type User,
} from '../lib/auth'

/** 'checking' only while a stored token is being confirmed on load. */
type AuthStatus = 'checking' | 'signed-out' | 'signed-in'

export interface UseAuthResult {
  status: AuthStatus
  user: User | null
  error: string | null
  login: (email: string, password: string) => Promise<void>
  signup: (name: string, email: string, password: string) => Promise<void>
  logout: () => void
}

export function useAuth(): UseAuthResult {
  // Starts at 'signed-out' with no token, so a first-time visitor never sees
  // a loading state before the landing page.
  const [status, setStatus] = useState<AuthStatus>(() =>
    readToken() ? 'checking' : 'signed-out',
  )
  const [user, setUser] = useState<User | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (status !== 'checking') return
    let cancelled = false

    fetchCurrentUser()
      .then((confirmed) => {
        if (cancelled) return
        setUser(confirmed)
        setStatus(confirmed ? 'signed-in' : 'signed-out')
      })
      .catch(() => {
        // The token may well be fine and the backend down; either way there
        // is nothing to show but the landing page.
        if (cancelled) return
        setStatus('signed-out')
      })

    return () => {
      cancelled = true
    }
    // Runs once: `status` leaves 'checking' on the first resolution and the
    // guard above makes any later run a no-op.
  }, [status])

  const run = useCallback(async (request: Promise<{ user: User }>) => {
    setError(null)
    try {
      const { user: authenticated } = await request
      setUser(authenticated)
      setStatus('signed-in')
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Something went wrong.'
      setError(message)
      // Rethrown so the form knows not to treat this as a success — it also
      // needs to stop its own submitting state.
      throw new Error(message, { cause: err })
    }
  }, [])

  return {
    status,
    user,
    error,
    login: useCallback(
      (email: string, password: string) => run(loginRequest(email, password)),
      [run],
    ),
    signup: useCallback(
      (name: string, email: string, password: string) => run(signupRequest(name, email, password)),
      [run],
    ),
    logout: useCallback(() => {
      logoutRequest()
      setUser(null)
      setError(null)
      setStatus('signed-out')
    }, []),
  }
}
