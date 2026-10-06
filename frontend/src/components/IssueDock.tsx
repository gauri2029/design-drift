import { useState } from 'react'
import type { FixDecision } from '../lib/api'
import { FIX_STATE, SEVERITY, issueHeadline, type Issue } from '../lib/issues'
import { useCursorLight } from '../lib/motion'
import { Button, Chevron, EmptyState, Label, Status } from './ui'

type Filter = 'all' | 'blocking' | 'todo' | 'done'

/** Every problem in one list, one line each until you open it.
 *
 * What it replaces: four stacked sections — findings, source locations,
 * proposed fixes, verification — each listing the same problems in a
 * different order, joined only by a title you matched up by eye. Here one
 * problem is one row, and opening it tells the whole story: what's wrong,
 * where it lives, what the agent would change, and whether that worked.
 *
 * The closed row is deliberately spare. Scanning, you need the headline and
 * how bad it is. File paths, rule ids and diffs are what you want *after*
 * deciding to act on something, so they live inside.
 */
export function IssueDock({
  issues,
  decisions,
  onDecide,
  openTitle,
  onOpenChange,
}: {
  issues: Issue[]
  decisions: Record<string, FixDecision>
  onDecide?: (title: string, decision: FixDecision) => void
  openTitle: string | null
  onOpenChange: (title: string | null) => void
}) {
  const [filter, setFilter] = useState<Filter>('all')

  if (issues.length === 0) {
    return <EmptyState title="Nothing to fix" body="This page matched its design on the last run." />
  }

  const isDone = (issue: Issue) =>
    issue.state === 'verified' || issue.state === 'already-present' || issue.state === 'rejected'

  const matches = (issue: Issue) => {
    if (filter === 'blocking') return issue.finding.priority === 'high'
    if (filter === 'todo') return !isDone(issue)
    if (filter === 'done') return isDone(issue)
    return true
  }

  const counts = {
    all: issues.length,
    blocking: issues.filter((i) => i.finding.priority === 'high').length,
    todo: issues.filter((i) => !isDone(i)).length,
    done: issues.filter(isDone).length,
  }

  const shown = issues.filter(matches)
  const labels: Record<Filter, string> = {
    all: 'Everything',
    blocking: 'Blocking',
    todo: 'To do',
    done: 'Done',
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-1.5" role="group" aria-label="Filter issues">
        {(Object.keys(labels) as Filter[]).map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => setFilter(id)}
            aria-pressed={filter === id}
            className={`tilt rounded-full border px-3.5 py-1.5 text-[13px] font-medium transition-colors duration-200 ${
              filter === id
                ? 'border-accent/45 bg-accent/15 text-accent-hi'
                : 'border-edge text-ink-faint hover:border-edge-hi hover:text-ink-dim'
            }`}
          >
            {labels[id]}
            <span className="ml-1.5 font-mono tabular-nums opacity-60">{counts[id]}</span>
          </button>
        ))}
      </div>

      <ul className="space-y-1.5">
        {shown.map((issue, index) => (
          <IssueRow
            key={issue.finding.title}
            issue={issue}
            index={index}
            open={openTitle === issue.finding.title}
            decision={decisions[issue.finding.title]}
            onToggle={() =>
              onOpenChange(openTitle === issue.finding.title ? null : issue.finding.title)
            }
            onDecide={onDecide}
          />
        ))}
      </ul>

      {shown.length === 0 && (
        <p className="rounded-2xl border border-dashed border-edge px-4 py-8 text-center text-[13px] text-ink-faint">
          Nothing here.
        </p>
      )}
    </div>
  )
}

function IssueRow({
  issue,
  index,
  open,
  decision,
  onToggle,
  onDecide,
}: {
  issue: Issue
  index: number
  open: boolean
  decision?: FixDecision
  onToggle: () => void
  onDecide?: (title: string, decision: FixDecision) => void
}) {
  const { finding, location, fix, state } = issue
  const fixState = FIX_STATE[state]
  const light = useCursorLight<HTMLLIElement>()

  const dot =
    finding.priority === 'high'
      ? 'bg-bad shadow-[0_0_10px_1px_var(--color-coral)]'
      : finding.priority === 'medium'
        ? 'bg-warn'
        : 'bg-ink-faint/50'

  return (
    <li
      onPointerMove={light.onPointerMove}
      className={`lit animate-rise overflow-hidden rounded-2xl border transition-colors duration-200 ${
        open
          ? 'border-accent/30 bg-raised'
          : 'tilt border-edge bg-tint hover:border-edge-hi hover:bg-raised'
      }`}
      // Each row arrives a beat after the one above, so the list assembles
      // rather than appearing. Capped, or a long list would crawl in.
      style={{ animationDelay: `${Math.min(index, 10) * 40}ms` }}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span aria-hidden="true" className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">
          {issueHeadline(issue)}
        </span>
        {/* Only states that ask something of you earn a chip in the closed
            row. The rest describe themselves once the row is open. */}
        {(state === 'pending' || state === 'unresolved' || state === 'verified') && (
          <Status tone={fixState.tone} size="sm">
            {fixState.label}
          </Status>
        )}
        <Chevron className={`text-ink-faint ${open ? 'rotate-90' : ''}`} />
      </button>

      {open && (
        <div className="animate-fade space-y-4 border-t border-edge px-4 py-4">
          <p className="flex flex-wrap items-center gap-x-2 font-mono text-[11px] uppercase tracking-[0.1em] text-ink-faint">
            <span>{SEVERITY[finding.priority].label}</span>
            <span aria-hidden="true">·</span>
            <span>{finding.source === 'accessibility' ? 'Accessibility' : 'Visual'}</span>
            {finding.likely_area && (
              <>
                <span aria-hidden="true">·</span>
                <span>{finding.likely_area}</span>
              </>
            )}
            {state !== 'no-fix' && state !== 'pending' && (
              <>
                <span aria-hidden="true">·</span>
                <span>{fixState.label}</span>
              </>
            )}
          </p>

          <p className="text-sm leading-relaxed text-ink-dim">{finding.detail}</p>

          {(state === 'no-fix' || state === 'manual') && (
            <p className="rounded-2xl border border-warn/25 bg-warn/8 px-4 py-3 text-[13px] text-warn">
              {state === 'no-fix'
                ? 'The agent found this in your code but no single edit would reliably fix it — this one needs your judgement.'
                : location && !location.no_match
                  ? 'Change this by hand: the right value is a design decision, not a pattern the agent can safely rewrite.'
                  : 'Change this by hand: the agent couldn’t find this in your source, so there’s nothing to patch.'}
            </p>
          )}

          {state === 'unresolved' && issue.verdictNote && (
            <p className="rounded-2xl border border-bad/25 bg-bad/8 px-4 py-3 text-[13px] text-bad">
              {issue.verdictNote}
            </p>
          )}

          {state === 'verified' && issue.verdictNote && (
            <p className="rounded-2xl border border-ok/25 bg-ok/8 px-4 py-3 text-[13px] text-ok">
              {issue.verdictNote}
            </p>
          )}

          {/* Kept but demoted: the rule id is the search term when you want
              the spec, and useless while scanning a list. */}
          {finding.source === 'accessibility' && (
            <p className="text-[13px] text-ink-faint">
              Rule <span className="font-mono text-ink-dim">{finding.title}</span> · reported as{' '}
              {finding.original_severity}
            </p>
          )}

          {location && !location.no_match && location.location && (
            <div>
              <Label>Where it lives</Label>
              <p className="mt-1.5 font-mono text-[13px] text-accent-hi">
                {location.location.file_path}:{location.location.line_start}
                {location.location.line_end !== location.location.line_start &&
                  `–${location.location.line_end}`}
              </p>
              <p className="mt-1 text-sm text-ink-dim">{location.explanation}</p>
              <details className="mt-2">
                <summary className="cursor-pointer text-[13px] text-ink-faint transition-colors hover:text-ink-dim">
                  Show the code
                </summary>
                <pre className="mt-2 overflow-x-auto rounded-2xl border border-edge bg-void p-3 font-mono text-xs text-ink-dim">
                  {location.location.code_evidence}
                </pre>
              </details>
            </div>
          )}

          {fix?.patch && (
            <div>
              <Label>The agent’s fix</Label>
              <p className="mt-1.5 text-sm text-ink-dim">{fix.explanation}</p>
              {!fix.original_code_found && (
                <p className="mt-2 text-[13px] text-warn">
                  The code this patch replaces isn’t in the file any more, so it can’t be applied as
                  written. Re-run to get a patch against the current file.
                </p>
              )}
              <details className="mt-2">
                <summary className="cursor-pointer text-[13px] text-ink-faint transition-colors hover:text-ink-dim">
                  Show the change
                </summary>
                <div className="mt-2 overflow-hidden rounded-2xl border border-edge font-mono text-xs">
                  <pre className="overflow-x-auto border-l-2 border-bad/60 bg-bad/8 p-3 text-ink-dim">
                    {fix.patch.original_code}
                  </pre>
                  <pre className="overflow-x-auto border-l-2 border-ok/60 bg-ok/8 p-3 text-ink-dim">
                    {fix.patch.replacement_code}
                  </pre>
                </div>
              </details>
            </div>
          )}

          {issue.backupPath && (
            <p className="text-[13px] text-ink-faint">
              Your original is saved at{' '}
              <span className="font-mono text-ink-dim">{issue.backupPath}</span>
            </p>
          )}

          {onDecide && state === 'pending' && fix?.patch && (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <Button
                size="sm"
                variant={decision === 'approved' ? 'primary' : 'secondary'}
                disabled={!fix.original_code_found}
                aria-pressed={decision === 'approved'}
                onClick={() => onDecide(finding.title, 'approved')}
              >
                {decision === 'approved' ? '✓ Approved' : 'Approve'}
              </Button>
              <Button
                size="sm"
                variant={decision === 'rejected' ? 'danger' : 'secondary'}
                aria-pressed={decision === 'rejected'}
                onClick={() => onDecide(finding.title, 'rejected')}
              >
                Skip
              </Button>
              {decision && (
                <span className="text-[13px] text-ink-faint">
                  Nothing is written until you apply.
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </li>
  )
}
