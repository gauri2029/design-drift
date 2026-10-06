import { useState } from 'react'
import { useDesignAnalyses } from '../hooks/useDesignAnalyses'
import {
  designAnalysisDiffUrl,
  designAnalysisProductionUrl,
  projectScreenshotUrl,
  verificationProductionUrl,
  type DesignAnalysis,
  type FixDecision,
  type Project,
} from '../lib/api'
import { buildIssues, issueHeadline, summarise, verdict, type Issue } from '../lib/issues'
import { useCursorLight, withViewTransition } from '../lib/motion'
import { DriftCanvas, type CanvasMode } from './DriftCanvas'
import { IssueDock } from './IssueDock'
import { Button, CountUp, EmptyState, Label, Status, Tabs } from './ui'

type View = 'drift' | 'fix' | 'runs'

/** The workspace for one project.
 *
 * Three views following the sequence of the work rather than the shape of
 * the backend: *Drift* is what changed, *Fix* is what to do about it, *Runs*
 * is what happened before. The page this replaces concatenated every agent's
 * output, so "is my page okay?" and "which patch am I approving?" lived in
 * the same scroll.
 */
export function Workspace({ project }: { project: Project }) {
  const {
    latestAnalysis,
    analyses,
    status,
    error,
    running,
    progress,
    runAnalysis,
    reviewFixes,
    applyFixes,
    verifyFixes,
  } = useDesignAnalyses(project.id)

  const [view, setView] = useState<View>('drift')
  const [runError, setRunError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [openIssue, setOpenIssue] = useState<string | null>(null)

  const analysis = analyses.find((a) => a.id === selectedId) ?? latestAnalysis
  const issues = analysis ? buildIssues(analysis) : []
  const counts = summarise(issues)

  const go = (next: View) => withViewTransition(() => setView(next))

  const run = async () => {
    setRunError(null)
    try {
      await runAnalysis()
      setSelectedId(null)
      setView('drift')
    } catch (err) {
      setRunError(err instanceof Error ? err.message : 'The run failed')
    }
  }

  return (
    <div className="min-w-0">
      <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <h1 className="truncate text-[28px] font-bold leading-tight text-ink">{project.name}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 font-mono text-[12px] text-ink-faint">
            <span className="truncate">{project.target_url}</span>
            {analysis && (
              <>
                <span aria-hidden="true">·</span>
                <span>{timeAgo(analysis.created_at)}</span>
              </>
            )}
          </p>
        </div>

        {/* Wraps on a phone: a tab group plus two controls doesn't fit one
            line at 390px, and overflowing is worse than a second row. */}
        <div className="flex w-full flex-wrap items-center gap-4 pe-1 sm:w-auto sm:gap-5">
          {analysis && (
            <Tabs
              label="Views"
              current={view}
              onChange={go}
              tabs={[
                { id: 'drift' as View, label: 'Drift' },
                { id: 'fix' as View, label: 'Fix', badge: counts.pending },
                { id: 'runs' as View, label: 'Runs' },
              ]}
            />
          )}
          <Button
            variant={counts.pending > 0 ? 'secondary' : 'primary'}
            onClick={() => void run()}
            disabled={running}
          >
            {running ? 'Running…' : analysis ? 'Run again' : 'Run check'}
          </Button>
        </div>
      </header>

      {running && (
        <div className="mt-6">
          <RunProgress progress={progress} />
        </div>
      )}

      {(error || runError) && (
        <p
          role="alert"
          className="animate-rise mt-6 rounded-2xl border border-bad/30 bg-bad/10 px-4 py-3 text-sm text-bad"
        >
          {runError ?? error}
        </p>
      )}

      {/* Named so the browser can tween between views rather than cut. */}
      <div className="mt-6" style={{ viewTransitionName: 'view' }}>
        {status === 'loading' && <p className="text-sm text-ink-faint">Loading…</p>}

        {status === 'ready' && !analysis && !running && (
          <EmptyState
            title="No check has run yet"
            body="A run opens a real browser and calls a model, so it never starts on its own."
            action={
              <Button variant="primary" size="lg" onClick={() => void run()}>
                Run the first check
              </Button>
            }
          />
        )}

        {analysis && view === 'drift' && (
          <Drift
            project={project}
            analysis={analysis}
            issues={issues}
            onGoFix={() => go('fix')}
            onOpenIssue={(title) => {
              setOpenIssue(title)
              go('fix')
            }}
          />
        )}

        {analysis && view === 'fix' && (
          <Fix
            project={project}
            analysis={analysis}
            issues={issues}
            openIssue={openIssue}
            onOpenIssue={setOpenIssue}
            onReview={reviewFixes}
            onApply={applyFixes}
            onVerify={verifyFixes}
          />
        )}

        {view === 'runs' && (
          <Runs
            analyses={analyses}
            selectedId={analysis?.id ?? null}
            onSelect={(id) => {
              setSelectedId(id)
              go('drift')
            }}
          />
        )}
      </div>
    </div>
  )
}

/** What the agents are doing, while they do it.
 *
 * A run is tens of seconds of browser work and model calls. A spinner can't
 * distinguish "working" from "hung", so each agent announces itself as it
 * finishes. Every line comes from a real SSE event — no invented stage list
 * padding it out, which is why it starts short and grows. */
function RunProgress({ progress }: { progress: { node: string; label: string }[] }) {
  return (
    <div className="glass animate-rise rounded-3xl px-6 py-5">
      <div className="flex items-center gap-3">
        <span className="relative grid h-9 w-9 shrink-0 place-items-center">
          <span className="animate-breathe absolute inset-0 rounded-full bg-accent/30" />
          <span className="relative h-2 w-2 rounded-full bg-accent" />
        </span>
        <div className="min-w-0">
          <p className="font-display text-base font-semibold text-ink">
            {progress.length === 0 ? 'Starting the run' : 'Checking your page'}
          </p>
          <p className="text-[13px] text-ink-faint">
            Opening a browser and calling the models — this takes a moment.
          </p>
        </div>
      </div>
      <ol className="mt-4 space-y-2">
        {progress.map((step) => (
          <li
            key={step.node}
            className="animate-rise flex items-center gap-2.5 text-[13px] text-ink-dim"
          >
            <span className="text-ok" aria-hidden="true">
              ✓
            </span>
            {step.label}
          </li>
        ))}
        <li className="flex items-center gap-2.5 text-[13px] text-ink">
          <span className="animate-breathe h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
          Working…
        </li>
      </ol>
    </div>
  )
}

/** The hero: the verdict, then the comparison at full width. */
function Drift({
  project,
  analysis,
  issues,
  onGoFix,
  onOpenIssue,
}: {
  project: Project
  analysis: DesignAnalysis
  issues: Issue[]
  onGoFix: () => void
  onOpenIssue: (title: string) => void
}) {
  const [mode, setMode] = useState<CanvasMode>('reveal')
  const counts = summarise(issues)
  const call = verdict(issues)
  const clean = counts.total === 0
  const dot = clean ? 'bg-ok' : counts.blocking > 0 ? 'bg-bad' : 'bg-warn'

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            {/* One ring, expanding outward once. A looping pulse on a status
                light is a cry for attention that never stops. */}
            <span aria-hidden="true" className="relative grid h-2.5 w-2.5 place-items-center">
              <span className={`animate-ping-once absolute inset-0 rounded-full ${dot}`} />
              <span className={`absolute inset-0 rounded-full ${dot}`} />
            </span>
            <h2 className="gradient-text truncate text-2xl font-bold">
              {call.count !== null && <CountUp value={call.count} />}
              {call.after}
            </h2>
          </div>
          <p className="mt-1.5 pl-[22px] text-sm text-ink-dim">{call.detail}</p>
        </div>

        {counts.pending > 0 && (
          <Button variant="primary" className="shrink-0" onClick={onGoFix}>
            Review {counts.pending} {counts.pending === 1 ? 'fix' : 'fixes'}
          </Button>
        )}
      </div>

      {analysis.production_screenshot_key ? (
        <DriftCanvas
          designSrc={projectScreenshotUrl(project.id)}
          productionSrc={designAnalysisProductionUrl(project.id, analysis.id)}
          diffSrc={
            analysis.diff_image_key ? designAnalysisDiffUrl(project.id, analysis.id) : undefined
          }
          mismatch={analysis.comparison_result?.mismatch_percentage}
          mode={mode}
          onModeChange={setMode}
        />
      ) : (
        <EmptyState title="This run captured no screenshot" />
      )}

      {issues.length > 0 && (
        <div>
          <div className="mb-3 flex items-baseline justify-between gap-3">
            <Label>Start here</Label>
            {issues.length > 3 && (
              <button
                type="button"
                onClick={onGoFix}
                className="text-[13px] text-ink-faint transition-colors hover:text-accent-hi"
              >
                All {issues.length} issues →
              </button>
            )}
          </div>
          {/* Three, not ten: a shortlist you read, rather than a list you
              start scrolling and may as well have opened Fix for. */}
          <ul className="grid gap-3 sm:grid-cols-3">
            {issues.slice(0, 3).map((issue, index) => (
              <IssueCard
                key={issue.finding.title}
                issue={issue}
                index={index}
                onClick={() => onOpenIssue(issue.finding.title)}
              />
            ))}
          </ul>
        </div>
      )}

      <details className="group overflow-hidden rounded-3xl border border-edge bg-tint">
        <summary className="cursor-pointer list-none px-5 py-4 text-sm text-ink-dim transition-colors hover:text-ink">
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="mr-2 inline-block h-3.5 w-3.5 align-[-2px] transition-transform duration-300 group-open:rotate-90"
          >
            <path d="m9 6 6 6-6 6" />
          </svg>
          What this design was trying to do
        </summary>
        <div className="space-y-2 border-t border-edge px-5 py-4">
          <p className="text-sm text-ink-dim">{analysis.result.design_intent}</p>
          <p className="text-sm text-ink-faint">{analysis.result.layout_summary}</p>
        </div>
      </details>
    </div>
  )
}

function IssueCard({
  issue,
  index,
  onClick,
}: {
  issue: Issue
  index: number
  onClick: () => void
}) {
  const tone =
    issue.finding.priority === 'high'
      ? 'bad'
      : issue.finding.priority === 'medium'
        ? 'warn'
        : 'neutral'
  const light = useCursorLight<HTMLButtonElement>()
  return (
    <li className="animate-rise" style={{ animationDelay: `${index * 60}ms` }}>
      <button
        type="button"
        onClick={onClick}
        onPointerMove={light.onPointerMove}
        className="lit tilt-lg h-full w-full rounded-3xl border border-edge bg-tint px-5 py-4 text-left transition-colors duration-200 hover:border-edge-hi hover:bg-raised"
      >
        <Status tone={tone} size="sm">
          {issue.finding.source === 'accessibility' ? 'Accessibility' : 'Visual'}
        </Status>
        <p className="mt-3 text-sm font-medium leading-snug text-ink">{issueHeadline(issue)}</p>
      </button>
    </li>
  )
}

/** Review, apply, verify — the three consequential steps, in order. */
function Fix({
  project,
  analysis,
  issues,
  openIssue,
  onOpenIssue,
  onReview,
  onApply,
  onVerify,
}: {
  project: Project
  analysis: DesignAnalysis
  issues: Issue[]
  openIssue: string | null
  onOpenIssue: (title: string | null) => void
  onReview: (
    id: string,
    decisions: { finding_title: string; decision: FixDecision }[],
  ) => Promise<void>
  onApply: (id: string) => Promise<void>
  onVerify: (id: string, targetUrl?: string) => Promise<void>
}) {
  const [decisions, setDecisions] = useState<Record<string, FixDecision>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [verifyUrl, setVerifyUrl] = useState('')
  const [verifyOpen, setVerifyOpen] = useState(false)

  const approved = Object.values(decisions).filter((d) => d === 'approved').length
  const written = (analysis.fix_application?.fixes ?? []).filter((f) => f.applied).length
  const unresolved = (analysis.verification?.findings ?? []).some((f) => f.verdict !== 'resolved')

  const act = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That didn’t work')
    } finally {
      setBusy(false)
    }
  }

  const saveAndApply = () =>
    act(async () => {
      await onReview(
        analysis.id,
        Object.entries(decisions).map(([finding_title, decision]) => ({ finding_title, decision })),
      )
      await onApply(analysis.id)
      setDecisions({})
    })

  return (
    <div>
      <IssueDock
        issues={issues}
        decisions={decisions}
        openTitle={openIssue}
        onOpenChange={onOpenIssue}
        onDecide={(title, decision) =>
          setDecisions((current) => ({ ...current, [title]: decision }))
        }
      />

      {error && (
        <p role="alert" className="animate-rise mt-4 text-[13px] text-bad">
          {error}
        </p>
      )}

      {/* The action dock. Floats above the list and appears only when there
          is something to do — a sticky side rail saying "approve something
          first" was a permanent column of instructions. */}
      {(approved > 0 || written > 0) && (
        <div className="sticky bottom-5 z-30 mt-5 flex justify-center">
          <div className="glass-deep animate-rise w-full max-w-2xl rounded-3xl p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="min-w-0 flex-1 text-[13px] leading-relaxed text-ink-dim">
                {written > 0 ? (
                  <>
                    <span className="font-medium text-ink">
                      {written} {written === 1 ? 'change' : 'changes'} written.
                    </span>{' '}
                    Nothing was staged, committed or pushed — your git history is the undo.
                  </>
                ) : (
                  <>
                    <span className="font-medium text-ink">
                      {approved} {approved === 1 ? 'fix' : 'fixes'} approved.
                    </span>{' '}
                    Nothing touches your files until you apply.
                  </>
                )}
              </p>
              <div className="flex shrink-0 gap-2">
                {written > 0 && (
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={busy}
                    onClick={() => setVerifyOpen((v) => !v)}
                    aria-expanded={verifyOpen}
                  >
                    {analysis.verification ? 'Verify again' : 'Verify'}
                  </Button>
                )}
                {approved > 0 && (
                  <Button variant="primary" disabled={busy} onClick={() => void saveAndApply()}>
                    {busy ? 'Applying…' : `Apply ${approved}`}
                  </Button>
                )}
                {written > 0 && approved === 0 && (
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() => void act(() => onApply(analysis.id))}
                  >
                    Apply again
                  </Button>
                )}
              </div>
            </div>

            {verifyOpen && written > 0 && (
              <div className="animate-fade mt-4 space-y-2.5 border-t border-edge pt-4">
                {/* The trap this step walks into: patches land in a local
                    checkout, so a deployed target shows nothing until it is
                    rebuilt. Say it before the run, not after. */}
                <p className="text-[13px] leading-relaxed text-ink-dim">
                  Re-checks the page after you rebuild it. Changes landed in your local files, so
                  point this at a dev server if your site is deployed.
                </p>
                <div className="flex flex-wrap gap-2">
                  <input
                    type="url"
                    value={verifyUrl}
                    onChange={(event) => setVerifyUrl(event.target.value)}
                    placeholder={project.target_url}
                    aria-label="URL to verify against"
                    className="min-w-0 flex-1 rounded-xl border border-edge bg-void/60 px-3 py-2 text-[13px] text-ink transition-colors placeholder:text-ink-faint/50 focus:border-accent/50"
                  />
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={busy}
                    onClick={() =>
                      void act(() => onVerify(analysis.id, verifyUrl.trim() || undefined))
                    }
                  >
                    {busy ? 'Verifying…' : 'Run it'}
                  </Button>
                </div>

                {analysis.verification && (
                  <div className="space-y-2 pt-1">
                    {/* An unchanged page cannot tell you anything about the
                        patches, and reading it as "the fix failed" would be
                        a confident wrong answer. */}
                    {!analysis.verification.production_changed && (
                      <p className="rounded-xl border border-warn/25 bg-warn/8 px-3 py-2.5 text-[13px] text-warn">
                        The page hasn’t changed since the run, so this says nothing about whether
                        the fixes worked. Rebuild, then verify again.
                      </p>
                    )}
                    <p className="text-[13px] text-ink-dim">{analysis.verification.summary}</p>
                    {unresolved && (
                      <Status tone="bad" size="sm">
                        Some fixes didn’t land
                      </Status>
                    )}
                    {analysis.verification_screenshot_key && (
                      <img
                        src={verificationProductionUrl(project.id, analysis.id)}
                        alt="The page after the fixes were applied"
                        className="mt-2 max-h-48 w-full rounded-xl border border-edge object-cover object-top"
                      />
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function Runs({
  analyses,
  selectedId,
  onSelect,
}: {
  analyses: DesignAnalysis[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  if (analyses.length === 0) return <EmptyState title="No runs yet" />

  return (
    <ul className="space-y-2">
      {analyses.map((analysis, index) => {
        const counts = summarise(buildIssues(analysis))
        const isSelected = analysis.id === selectedId
        return (
          <li
            key={analysis.id}
            className="animate-rise"
            style={{ animationDelay: `${index * 40}ms` }}
          >
            <button
              type="button"
              onClick={() => onSelect(analysis.id)}
              aria-current={isSelected ? 'true' : undefined}
              className={`tilt flex w-full flex-wrap items-center gap-x-3 gap-y-1 rounded-2xl border px-5 py-4 text-left transition-colors duration-200 ${
                isSelected
                  ? 'border-accent/40 bg-accent/10'
                  : 'border-edge bg-tint hover:border-edge-hi hover:bg-raised'
              }`}
            >
              <span className="text-sm font-medium text-ink">{timeAgo(analysis.created_at)}</span>
              <span className="font-mono text-[12px] text-ink-faint">
                {counts.total === 0
                  ? 'clean'
                  : `${counts.total} ${counts.total === 1 ? 'issue' : 'issues'}`}
                {counts.blocking > 0 && `, ${counts.blocking} blocking`}
                {counts.fixed > 0 && ` · ${counts.fixed} fixed`}
              </span>
              {isSelected && (
                <span className="ml-auto">
                  <Status tone="accent" size="sm">
                    Showing
                  </Status>
                </span>
              )}
            </button>
          </li>
        )
      })}
    </ul>
  )
}

/** "2 hours ago", not a timestamp. For a QA run, how recent it is is the
 * whole question and the exact minute almost never is. */
function timeAgo(iso: string): string {
  const then = new Date(iso)
  const minutes = Math.round((Date.now() - then.getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'} ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} ${hours === 1 ? 'hour' : 'hours'} ago`
  const days = Math.round(hours / 24)
  if (days <= 7) return `${days} ${days === 1 ? 'day' : 'days'} ago`
  return then.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
