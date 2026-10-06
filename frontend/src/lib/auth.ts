/** Sign-in, sign-up, and the stored token.
 *
 * Kept out of api.ts because nothing else in that file needs a token: no
 * existing endpoint is gated, so threading an Authorization header through
 * every request would be ceremony around a value the backend ignores. When
 * projects gain an owner, `authHeader()` below is what those calls pick up.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// localStorage rather than a cookie: the API is a separate origin and issues
// a bearer token, so there is no cookie for the browser to attach. The
// tradeoff is honest — a token here is readable by any script that gets onto
// the page, which is why it expires server-side rather than being trusted
// indefinitely.
const TOKEN_KEY = 'design-drift.token'

/** Mirrors app/schemas/auth.py:UserRead. */
export interface User {
  id: string
  email: string
  name: string
  created_at: string
}

interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export function readToken(): string | null {
  // Wrapped because localStorage throws outright in a Safari private window
  // and in some embedded webviews, and a landing page must still render.
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function writeToken(token: string | null): void {
  try {
    if (token === null) localStorage.removeItem(TOKEN_KEY)
    else localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // A session that can't be persisted still works until reload.
  }
}

/** The header to send on a request that needs the signed-in user. */
export function authHeader(): Record<string, string> {
  const token = readToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** The API's `detail`, or a readable fallback.
 *
 * FastAPI returns `detail` as a string for our own HTTPExceptions but as an
 * array of per-field objects for a 422, and rendering that array raw would
 * put "[object Object]" in front of someone trying to sign up.
 */
async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) {
      const first = body.detail[0] as { msg?: string } | undefined
      if (first?.msg) return first.msg
    }
  } catch {
    // Not JSON — a proxy error page or an empty body.
  }
  return fallback
}

async function post(path: string, body: unknown, fallback: string): Promise<TokenResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(await errorMessage(response, fallback))
  }
  const data = (await response.json()) as TokenResponse
  writeToken(data.access_token)
  return data
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return post('login', { email, password }, 'Could not sign in. Please try again.')
}

export function signup(name: string, email: string, password: string): Promise<TokenResponse> {
  return post('signup', { name, email, password }, 'Could not create your account.')
}

/** Who the stored token belongs to, or null if there isn't a usable one.
 *
 * Returns null for an expired or revoked token as well as for no token at
 * all, and clears it on the way out, so a stale token doesn't leave the app
 * showing a signed-in shell it can't use.
 */
export async function fetchCurrentUser(): Promise<User | null> {
  const token = readToken()
  if (!token) return null

  const response = await fetch(`${API_BASE_URL}/api/v1/auth/me`, { headers: authHeader() })
  if (response.status === 401) {
    writeToken(null)
    return null
  }
  if (!response.ok) {
    // A 500 or an unreachable backend is not evidence the token is bad, so
    // it's kept — this surfaces as an error rather than a silent sign-out.
    throw new Error('Could not confirm your session.')
  }
  return (await response.json()) as User
}

export function logout(): void {
  writeToken(null)
}
