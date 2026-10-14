import { useEffect, useState } from 'react'
import {
  fetchBranches,
  fetchGitHubStatus,
  fetchInstallations,
  fetchRepositories,
  linkInstallation,
  linkInstallationByAccount,
  type Installation,
  type Repository,
} from '../lib/github'
import { Label } from './ui'

export interface GitHubSelection {
  repoFullName: string
  branch: string
}

/** Pick a repository and branch from the user's GitHub App installations.
 *
 * Read-only throughout. The App holds `Contents: read-only`, so nothing
 * here - or anywhere else in Design Drift - can push, commit or open a
 * pull request.
 */
export function GitHubSource({
  value,
  onChange,
}: {
  value: GitHubSelection | null
  onChange: (selection: GitHubSelection | null) => void
}) {
  const [configured, setConfigured] = useState<boolean | null>(null)
  const [installUrl, setInstallUrl] = useState<string | null>(null)
  const [installations, setInstallations] = useState<Installation[]>([])
  const [installationId, setInstallationId] = useState<number | null>(null)
  const [repositories, setRepositories] = useState<Repository[]>([])
  const [branches, setBranches] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [account, setAccount] = useState('')
  const [linking, setLinking] = useState(false)

  // GitHub redirects back with ?installation_id=... after an install.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('installation_id')
    if (!id) return
    void linkInstallation(Number(id))
      .then((record) => {
        setInstallations((current) =>
          current.some((i) => i.installation_id === record.installation_id)
            ? current
            : [record, ...current],
        )
        setInstallationId(record.installation_id)
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Link failed'))
      .finally(() => {
        // Clear the param so a reload doesn't re-post it.
        window.history.replaceState(null, '', window.location.pathname)
      })
  }, [])

  useEffect(() => {
    void fetchGitHubStatus()
      .then((status) => {
        setConfigured(status.configured)
        setInstallUrl(status.install_url)
        if (status.configured) return fetchInstallations().then(setInstallations)
      })
      .catch(() => setConfigured(false))
  }, [])

  useEffect(() => {
    if (installationId === null) return
    void fetchRepositories(installationId)
      .then(setRepositories)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : 'Could not list repositories'),
      )
  }, [installationId])

  useEffect(() => {
    if (installationId === null || !value?.repoFullName) return
    void fetchBranches(installationId, value.repoFullName).then(setBranches).catch(() => {})
  }, [installationId, value?.repoFullName])

  if (configured === null) return null

  if (!configured) {
    return (
      <p className="text-[13px] text-ink-faint">
        GitHub isn’t set up on this server. Use a local source path below instead.
      </p>
    )
  }

  return (
    <div className="space-y-3">
      {installations.length === 0 ? (
        <div className="space-y-2">
          <p className="text-[13px] text-ink-dim">
            Connect a repository so Design Drift can read your source and point findings at the
            lines that caused them.
          </p>
          {installUrl && (
            <a
              href={installUrl}
              className="inline-flex items-center gap-2 rounded-xl border border-edge-hi bg-tint px-3.5 py-2 text-[13px] text-ink transition-colors duration-200 hover:bg-raised"
            >
              Connect GitHub
            </a>
          )}

          {/* GitHub's "Configure" flow returns here without an
              installation_id, so someone who already installed the App
              lands back on this screen with no way forward. Naming the
              account they installed it on recovers it. */}
          <details className="text-[13px] text-ink-faint">
            <summary className="cursor-pointer transition-colors duration-200 hover:text-ink-dim">
              Already installed it?
            </summary>
            <div className="mt-2.5 flex gap-2">
              <input
                value={account}
                onChange={(event) => setAccount(event.target.value)}
                placeholder="your-github-username"
                aria-label="GitHub account you installed it on"
                className="min-w-0 flex-1 rounded-xl border border-edge-hi bg-tint px-3 py-2 text-[13px] text-ink placeholder:text-ink-faint/60 focus:border-accent focus:outline-none"
              />
              <button
                type="button"
                disabled={!account.trim() || linking}
                onClick={() => {
                  setLinking(true)
                  setError(null)
                  void linkInstallationByAccount(account.trim())
                    .then((record) => {
                      setInstallations((current) => [record, ...current])
                      setInstallationId(record.installation_id)
                      setAccount('')
                    })
                    .catch((err: unknown) =>
                      setError(err instanceof Error ? err.message : 'Could not link that'),
                    )
                    .finally(() => setLinking(false))
                }}
                className="shrink-0 rounded-xl border border-edge-hi bg-tint px-3 py-2 text-[13px] text-ink transition-colors duration-200 hover:bg-raised disabled:opacity-40"
              >
                {linking ? 'Linking…' : 'Link'}
              </button>
            </div>
          </details>
        </div>
      ) : (
        <>
          <label className="block">
            <span className="mb-1.5 block text-[13px] font-medium text-ink-dim">Account</span>
            <select
              value={installationId ?? ''}
              onChange={(event) => {
                setInstallationId(Number(event.target.value))
                setError(null)
                onChange(null)
              }}
              className="w-full rounded-xl border border-edge-hi bg-tint px-3.5 py-2.5 text-sm text-ink"
            >
              <option value="">Choose an account…</option>
              {installations.map((i) => (
                <option key={i.installation_id} value={i.installation_id}>
                  {i.account_login}
                </option>
              ))}
            </select>
          </label>

          {repositories.length > 0 && (
            <label className="block">
              <span className="mb-1.5 block text-[13px] font-medium text-ink-dim">Repository</span>
              <select
                value={value?.repoFullName ?? ''}
                onChange={(event) => {
                  const repo = repositories.find((r) => r.full_name === event.target.value)
                  onChange(
                    repo ? { repoFullName: repo.full_name, branch: repo.default_branch } : null,
                  )
                }}
                className="w-full rounded-xl border border-edge-hi bg-tint px-3.5 py-2.5 text-sm text-ink"
              >
                <option value="">Choose a repository…</option>
                {repositories.map((r) => (
                  // Private repositories are shown but not selectable, so
                  // someone who installed the App on one can see why.
                  <option key={r.full_name} value={r.full_name} disabled={!r.analyzable}>
                    {r.full_name}
                    {r.analyzable ? '' : ' - private, not supported yet'}
                  </option>
                ))}
              </select>
            </label>
          )}

          {value && branches.length > 0 && (
            <label className="block">
              <span className="mb-1.5 block text-[13px] font-medium text-ink-dim">Branch</span>
              <select
                value={value.branch}
                onChange={(event) => onChange({ ...value, branch: event.target.value })}
                className="w-full rounded-xl border border-edge-hi bg-tint px-3.5 py-2.5 text-sm text-ink"
              >
                {branches.map((branch) => (
                  <option key={branch} value={branch}>
                    {branch}
                  </option>
                ))}
              </select>
            </label>
          )}

          {value && (
            /* Stated at the point of consent, not buried in a policy: this
               is the moment someone's code starts going to a third party. */
            <div className="rounded-xl border border-warn/30 bg-warn/10 px-3.5 py-2.5">
              <Label>What happens to this code</Label>
              <ul className="mt-2 space-y-1.5 text-[13px] leading-relaxed text-ink-dim">
                <li>
                  Each run clones this branch into a temporary folder. Only the few snippets that
                  match a finding are sent to your AI provider, not the whole repository.
                </li>
                <li>
                  Only UI source files are read. Never <code>.env</code> files, keys, build output
                  or anything outside the checkout.
                </li>
                <li>Nothing is written back to GitHub. No commits, no branches, no pull requests.</li>
              </ul>
            </div>
          )}
        </>
      )}

      {error && (
        <p role="alert" className="text-[13px] text-bad">
          {error}
        </p>
      )}
    </div>
  )
}
