import { useState } from 'react'
import { useDesignAnalyses } from '../hooks/useDesignAnalyses'
import {
  designAnalysisDiffUrl,
  designAnalysisProductionUrl,
  projectScreenshotUrl,
  type AggregatedFinding,
  type DesignAnalysis,
  type FindingLocation,
  type FindingPriority,
  type FixDecision,
  type FixDecisionItem,
  type Project,
  type VerifiedFix,
} from '../lib/api'
import { Badge, type BadgeTone } from './Badge'
import { ZoomableImage } from './ZoomableImage'

interface DesignQAPanelProps {
  project: Project
}

/** The LangGraph Design QA workflow — project-scoped, unlike Scan/Review.
 *
 * One run drives every agent in app/graph/workflow.py: Figma analysis,
 * production capture, visual comparison, accessibility, findings
 * aggregation, and (conditionally) code analysis. It captures production
 * itself rather than reusing a Scan, which is why this sits beside the
 * scan section rather than inside it.
 */
export function DesignQAPanel({ project }: DesignQAPanelProps) {
  const { latestAnalysis, status, error, running, runAnalysis, reviewFixes } = useDesignAnalyses(
    project.id,
  )
  // runAnalysis rethrows (same convention as useScans/useReviews), so the
  // failure message is held here rather than in the hook.
  const [runError, setRunError] = useState<string | null>(null)

  const run = async () => {
    setRunError(null)
    try {
      await runAnalysis()
    } catch (err) {
      setRunError(err instanceof Error ? err.message : 'Failed to run the Design QA workflow')
    }
  }

  return (
    <section className="mt-8 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Design QA workflow
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            One multi-agent run: analyzes the Figma design, captures production, compares them,
            checks accessibility, then locates the code behind what it finds. Costs real money
            per run, so it never starts on its own.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void run()}
          disabled={running}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? 'Running workflow…' : 'Run Design QA'}
        </button>
      </div>

      {status === 'loading' && (
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>
      )}
      {(error || runError) && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {runError ?? error}
        </p>
      )}

      {status === 'ready' && !latestAnalysis && !running && (
        <p className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
          No workflow run yet for this project.
        </p>
      )}

      {latestAnalysis && (
        <AnalysisResult project={project} analysis={latestAnalysis} onReview={reviewFixes} />
      )}
    </section>
  )
}

function AnalysisResult({
  project,
  analysis,
  onReview,
}: {
  project: Project
  analysis: DesignAnalysis
  onReview: (analysisId: string, decisions: FixDecisionItem[]) => Promise<void>
}) {
  return (
    <div className="space-y-5 rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
        <Badge tone="info">{analysis.model}</Badge>
        <span>{new Date(analysis.created_at).toLocaleString()}</span>
      </div>

      <Section title="Findings">
        <FindingsList analysis={analysis} />
      </Section>

      <Section title="Source locations">
        <CodeAnalysis analysis={analysis} project={project} />
      </Section>

      <Section title="Proposed fixes">
        {/* Keyed on the run so a fresh run starts from its own review
            state rather than inheriting the previous run's choices. */}
        <FixProposal key={analysis.id} analysis={analysis} onReview={onReview} />
      </Section>

      <Section title="Design intent (Figma)">
        <p className="text-sm text-slate-700 dark:text-slate-300">
          {analysis.result.design_intent}
        </p>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          {analysis.result.layout_summary}
        </p>
        {analysis.result.implementation_risks.length > 0 && (
          <ul className="mt-2 list-inside list-disc text-sm text-slate-600 dark:text-slate-400">
            {analysis.result.implementation_risks.map((risk) => (
              <li key={risk}>{risk}</li>
            ))}
          </ul>
        )}
      </Section>

      {analysis.production_screenshot_key && analysis.diff_image_key && (
        <Section title="Captured comparison">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Figure label="Figma (expected)" src={projectScreenshotUrl(project.id)} />
            <Figure
              label="Production (actual)"
              src={designAnalysisProductionUrl(project.id, analysis.id)}
            />
            <Figure label="Diff" src={designAnalysisDiffUrl(project.id, analysis.id)} />
          </div>
        </Section>
      )}
    </div>
  )
}

function FindingsList({ analysis }: { analysis: DesignAnalysis }) {
  const aggregated = analysis.aggregated_findings

  if (!aggregated || !aggregated.problems_found) {
    return (
      <p className="text-sm text-emerald-700 dark:text-emerald-400">
        No material problems found.
      </p>
    )
  }

  if (aggregated.findings.length === 0) {
    // problems_found can be true with nothing itemized — the Visual
    // Comparison Agent's overall verdict counts on its own.
    return (
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Drift was detected, but no individual findings were itemized.
      </p>
    )
  }

  return (
    <ul className="space-y-2">
      {aggregated.findings.map((finding, index) => (
        <li
          key={`${finding.source}-${finding.title}-${index}`}
          className="rounded-md border border-slate-200 p-3 text-sm dark:border-slate-800"
        >
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={priorityTone(finding.priority)}>{finding.priority}</Badge>
            <Badge>{finding.source.replace('_', ' ')}</Badge>
            <span className="font-medium text-slate-900 dark:text-slate-100">{finding.title}</span>
          </div>
          <p className="mt-1 text-slate-600 dark:text-slate-400">{finding.detail}</p>
          <FindingFooter finding={finding} />
        </li>
      ))}
    </ul>
  )
}

function FindingFooter({ finding }: { finding: AggregatedFinding }) {
  return (
    <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
      Reported as “{finding.original_severity}”
      {finding.likely_area && ` · ${finding.likely_area}`}
    </p>
  )
}

function CodeAnalysis({ analysis, project }: { analysis: DesignAnalysis; project: Project }) {
  if (!analysis.code_analysis) {
    // The workflow forks here (see app/agents/supervisor.py), so absence is
    // a real outcome worth explaining rather than an empty panel.
    const reason = !project.source_path
      ? 'This project has no source checkout configured, so the code analysis step was skipped.'
      : 'No problems were found, so the code analysis step was skipped.'
    return <p className="text-sm text-slate-500 dark:text-slate-400">{reason}</p>
  }

  return (
    <div className="space-y-2">
      <p className="text-sm text-slate-600 dark:text-slate-400">{analysis.code_analysis.summary}</p>
      <ul className="space-y-2">
        {analysis.code_analysis.locations.map((location, index) => (
          <LocationItem key={`${location.finding_title}-${index}`} location={location} />
        ))}
      </ul>
    </div>
  )
}

function LocationItem({ location }: { location: FindingLocation }) {
  return (
    <li className="rounded-md border border-slate-200 p-3 text-sm dark:border-slate-800">
      <div className="flex flex-wrap items-center gap-2">
        {location.no_match ? (
          <Badge tone="neutral">no match</Badge>
        ) : (
          <Badge tone={confidenceTone(location.confidence)}>{location.confidence} confidence</Badge>
        )}
        <span className="font-medium text-slate-900 dark:text-slate-100">
          {location.finding_title}
        </span>
      </div>

      {location.location && (
        <>
          <p className="mt-1 font-mono text-xs text-indigo-700 dark:text-indigo-300">
            {location.location.file_path}:{location.location.line_start}
            {location.location.line_end !== location.location.line_start &&
              `-${location.location.line_end}`}
          </p>
          <pre className="mt-1 overflow-x-auto rounded bg-slate-100 p-2 text-xs text-slate-800 dark:bg-slate-950 dark:text-slate-200">
            <code>{location.location.code_evidence}</code>
          </pre>
        </>
      )}

      <p className="mt-1 text-slate-600 dark:text-slate-400">{location.explanation}</p>
    </li>
  )
}

function FixProposal({
  analysis,
  onReview,
}: {
  analysis: DesignAnalysis
  onReview: (analysisId: string, decisions: FixDecisionItem[]) => Promise<void>
}) {
  const review = analysis.fix_review
  const [decisions, setDecisions] = useState<Record<string, FixDecision>>(() =>
    Object.fromEntries((review?.decisions ?? []).map((item) => [item.finding_title, item.decision])),
  )
  const [saving, setSaving] = useState(false)
  const [reviewError, setReviewError] = useState<string | null>(null)

  if (!analysis.fix_proposal) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        No patches proposed — nothing was located in the source to change.
      </p>
    )
  }

  const fixes = analysis.fix_proposal.fixes
  // Only a fix that actually carries a patch is a decision to make; the
  // ones the agent declined are shown, but there's nothing to sign off on.
  const reviewable = fixes.filter((fix) => !fix.no_fix && fix.patch)
  const pending = reviewable.filter((fix) => !decisions[fix.finding_title])

  const save = async () => {
    setSaving(true)
    setReviewError(null)
    try {
      await onReview(
        analysis.id,
        reviewable
          .filter((fix) => decisions[fix.finding_title])
          .map((fix) => ({ finding_title: fix.finding_title, decision: decisions[fix.finding_title] })),
      )
    } catch (err) {
      setReviewError(err instanceof Error ? err.message : 'Failed to save the review')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-sm text-slate-600 dark:text-slate-400">{analysis.fix_proposal.summary}</p>
      {/* Say plainly what approving does today. It records a decision — it
          does not touch the checkout (docs/principles.md #5). */}
      <p className="text-xs text-slate-500 dark:text-slate-500">
        Proposals only. Approving records your sign-off; nothing is written to your files, and
        nothing is ever committed or pushed.
      </p>

      {reviewable.length > 0 && (
        <ReviewBar
          review={review}
          pendingCount={pending.length}
          saving={saving}
          disabled={reviewable.every((fix) => !decisions[fix.finding_title])}
          onSave={() => void save()}
        />
      )}
      {reviewError && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {reviewError}
        </p>
      )}

      <ul className="space-y-2">
        {fixes.map((fix, index) => (
          <FixItem
            key={`${fix.finding_title}-${index}`}
            fix={fix}
            decision={decisions[fix.finding_title]}
            onDecide={(decision) =>
              setDecisions((current) => ({ ...current, [fix.finding_title]: decision }))
            }
          />
        ))}
      </ul>
    </div>
  )
}

function ReviewBar({
  review,
  pendingCount,
  saving,
  disabled,
  onSave,
}: {
  review: DesignAnalysis['fix_review']
  pendingCount: number
  saving: boolean
  disabled: boolean
  onSave: () => void
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-950">
      <p className="text-xs text-slate-600 dark:text-slate-400">
        {review
          ? `Reviewed ${new Date(review.reviewed_at).toLocaleString()}`
          : 'Awaiting your review'}
        {pendingCount > 0 && ` · ${pendingCount} undecided`}
      </p>
      <button
        type="button"
        onClick={onSave}
        disabled={saving || disabled}
        className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-900"
      >
        {saving ? 'Saving…' : review ? 'Update review' : 'Save review'}
      </button>
    </div>
  )
}

function FixItem({
  fix,
  decision,
  onDecide,
}: {
  fix: VerifiedFix
  decision: FixDecision | undefined
  onDecide: (decision: FixDecision) => void
}) {
  return (
    <li className="rounded-md border border-slate-200 p-3 text-sm dark:border-slate-800">
      <div className="flex flex-wrap items-center gap-2">
        {fix.no_fix ? (
          <Badge tone="neutral">no fix</Badge>
        ) : (
          <Badge tone={confidenceTone(fix.confidence)}>{fix.confidence} confidence</Badge>
        )}
        {/* A patch can read convincingly and still target code that isn't
            there. The check is ours, so surface it rather than letting a
            reviewer discover it by trying to apply the change. */}
        {fix.patch && !fix.original_code_found && (
          <Badge tone="danger">does not match current file</Badge>
        )}
        {decision && (
          <Badge tone={decision === 'approved' ? 'success' : 'neutral'}>{decision}</Badge>
        )}
        <span className="font-medium text-slate-900 dark:text-slate-100">{fix.finding_title}</span>
      </div>

      {fix.patch && (
        <>
          <p className="mt-1 font-mono text-xs text-indigo-700 dark:text-indigo-300">
            {fix.patch.file_path}:{fix.patch.line_start}
            {fix.patch.line_end !== fix.patch.line_start && `-${fix.patch.line_end}`}
          </p>
          <pre className="mt-1 overflow-x-auto rounded border-l-2 border-red-400 bg-red-50 p-2 text-xs text-slate-800 dark:bg-red-950/30 dark:text-slate-200">
            <code>{fix.patch.original_code}</code>
          </pre>
          <pre className="mt-1 overflow-x-auto rounded border-l-2 border-emerald-400 bg-emerald-50 p-2 text-xs text-slate-800 dark:bg-emerald-950/30 dark:text-slate-200">
            <code>{fix.patch.replacement_code}</code>
          </pre>
        </>
      )}

      <p className="mt-1 text-slate-600 dark:text-slate-400">{fix.explanation}</p>

      {!fix.no_fix && fix.patch && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <DecisionButton
            label="Approve"
            active={decision === 'approved'}
            // A patch we already know doesn't match the file can't be
            // approved — the backend refuses it, so don't offer it here.
            disabled={!fix.original_code_found}
            activeClass="border-emerald-500 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
            onClick={() => onDecide('approved')}
          />
          <DecisionButton
            label="Reject"
            active={decision === 'rejected'}
            disabled={false}
            activeClass="border-slate-500 bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200"
            onClick={() => onDecide('rejected')}
          />
          {!fix.original_code_found && (
            <span className="text-xs text-slate-500 dark:text-slate-500">
              Can’t be approved — re-run the workflow to get a patch against the current file.
            </span>
          )}
        </div>
      )}
    </li>
  )
}

function DecisionButton({
  label,
  active,
  disabled,
  activeClass,
  onClick,
}: {
  label: string
  active: boolean
  disabled: boolean
  activeClass: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={`rounded-md border px-3 py-1 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
        active
          ? activeClass
          : 'border-slate-300 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800'
      }`}
    >
      {label}
    </button>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {title}
      </h3>
      {children}
    </div>
  )
}

function Figure({ label, src }: { label: string; src: string }) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <ZoomableImage src={src} alt={label} />
    </div>
  )
}

function priorityTone(priority: FindingPriority): BadgeTone {
  switch (priority) {
    case 'high':
      return 'danger'
    case 'medium':
      return 'warning'
    default:
      return 'neutral'
  }
}

function confidenceTone(confidence: FindingLocation['confidence'] | VerifiedFix['confidence']): BadgeTone {
  switch (confidence) {
    case 'high':
      return 'success'
    case 'medium':
      return 'warning'
    default:
      return 'neutral'
  }
}
