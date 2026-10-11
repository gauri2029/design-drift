import { authHeader } from './auth'

/** Read-only GitHub browsing: installations, repositories, branches.
 *
 * Every call is authenticated and scoped server-side to the signed-in
 * user's own installations — this module can't widen that, it only asks.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export interface GitHubStatus {
  configured: boolean
  install_url: string | null
}

export interface Installation {
  installation_id: number
  account_login: string
}

export interface Repository {
  full_name: string
  private: boolean
  default_branch: string
  // False while private-repository analysis is deferred. The picker shows
  // the repo and disables it, rather than hiding it — someone who installed
  // the App on a private repo should see why it isn't selectable.
  analyzable: boolean
  reason: string | null
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/v1/github${path}`, { headers: authHeader() })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `GitHub request failed (${response.status})`)
  }
  return (await response.json()) as T
}

export function fetchGitHubStatus(): Promise<GitHubStatus> {
  return get<GitHubStatus>('/status')
}

export function fetchInstallations(): Promise<Installation[]> {
  return get<Installation[]>('/installations')
}

export function fetchRepositories(installationId: number): Promise<Repository[]> {
  return get<Repository[]>(`/installations/${installationId}/repositories`)
}

export function fetchBranches(installationId: number, fullName: string): Promise<string[]> {
  return get<string[]>(`/installations/${installationId}/repositories/${fullName}/branches`)
}

/** Record an installation after GitHub redirects back.
 *
 * The id comes from the callback's query string; the backend verifies it
 * with GitHub and refuses one already linked to another account.
 */
export async function linkInstallation(installationId: number): Promise<Installation> {
  const response = await fetch(`${API_BASE_URL}/api/v1/github/installations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader() },
    body: JSON.stringify({ installation_id: installationId }),
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `Could not link that installation (${response.status})`)
  }
  return (await response.json()) as Installation
}
