import { useState } from 'react'
import {
  designAnalysisProductionUrl,
  verificationProductionUrl,
  type DesignAnalysis,
  type FindingVerification,
  type Project,
  type VerificationResult,
} from '../lib/api'
import { Badge, type BadgeTone } from './Badge'
import { ZoomableImage } from './ZoomableImage'

interface VerificationSectionProps {
  project: Project
  analysis: DesignAnalysis
  onVerify: (analysisId: string, targetUrl?: string) => Promise<void>
}

/** "Did those applied patches actually work?" — the last step of the
 * workflow (see docs/architecture.md).
 *
 * Only meaningful once something was written to a file, so it stays
 * hidden until then rather than showing a disabled control with no
 * explanation.
 */
export function VerificationSection({ project, analysis, onVerify }: VerificationSectionProps) {
  const [targetUrl, setTargetUrl] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!analysis.fix_application?.fixes.some((fix) => fix.applied)) {
    return null
  }

  const verify = async () => {
    setVerifying(true)
    setError(null)
    try {
      await onVerify(analysis.id, targetUrl.trim() || undefined)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to verify the applied fixes')
    } finally {
      setVerifying(false)
    }
  }

  return (
    <div className="space-y-3">
      {/* The trap this step can walk into: patches land in a local
          checkout, so a deployed target shows nothing until it's rebuilt.
          Say it before the run, not after. */}
      <p className="text-xs text-slate-500 dark:text-slate-500">
        Re-captures the page, re-runs the accessibility scan and the diff, then judges each
        patched finding. Patches were written to your local files, so point this at a dev server
        if your target URL is a deployed site that hasn’t been rebuilt yet.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <input
          type="url"
          value={targetUrl}
          onChange={(event) => setTargetUrl(event.target.value)}
          placeholder={project.target_url}
          aria-label="URL to verify against"
          className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
        />
        <button
          type="button"
          onClick={() => void verify()}
          disabled={verifying}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {verifying ? 'Verifying…' : analysis.verification ? 'Verify again' : 'Verify fixes'}
        </button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      {analysis.verification && (
        <VerificationReport project={project} analysis={analysis} result={analysis.verification} />
      )}
    </div>
  )
}

function VerificationReport({
  project,
  analysis,
  result,
}: {
  project: Project
  analysis: DesignAnalysis
  result: VerificationResult
}) {
  return (
    <div className="space-y-3">
      {/* An unchanged page can't tell you anything about the patches, and
          reading it as "the fix failed" would be a confident wrong
          answer — so it gets said first and loudly. */}
      {!result.production_changed && (
        <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          The page did not change at all since the original run, so this tells you nothing about
          whether the patches worked.
        </p>
      )}

      <p className="text-sm text-slate-700 dark:text-slate-300">{result.summary}</p>

      <Measurements result={result} />

      {result.findings.length > 0 && (
        <ul className="space-y-2">
          {result.findings.map((finding, index) => (
            <VerdictItem key={`${finding.finding_title}-${index}`} finding={finding} />
          ))}
        </ul>
      )}

      {result.regressions.length > 0 && (
        <div className="rounded-md border border-red-300 bg-red-50 p-3 dark:border-red-900 dark:bg-red-950/30">
          <p className="text-xs font-medium uppercase tracking-wide text-red-800 dark:text-red-300">
            Regressions
          </p>
          <ul className="mt-1 list-inside list-disc text-sm text-red-800 dark:text-red-300">
            {result.regressions.map((regression) => (
              <li key={regression}>{regression}</li>
            ))}
          </ul>
        </div>
      )}

      {analysis.verification_screenshot_key && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Figure
            label="Before the fixes"
            src={designAnalysisProductionUrl(project.id, analysis.id)}
          />
          <Figure label="After the fixes" src={verificationProductionUrl(project.id, analysis.id)} />
        </div>
      )}
    </div>
  )
}

/** The deterministic half — measured, not judged. Shown next to the
 * verdicts so a reader can check one against the other. */
function Measurements({ result }: { result: VerificationResult }) {
  const delta = result.accessibility_delta
  return (
    <dl className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-3">
      <Measurement
        label="Pixel mismatch vs. design"
        value={`${result.mismatch_percentage_before.toFixed(2)}% → ${result.mismatch_percentage_after.toFixed(2)}%`}
      />
      <Measurement
        label="Accessibility rules fixed"
        value={delta.resolved_rule_ids.length ? delta.resolved_rule_ids.join(', ') : 'none'}
      />
      <Measurement
        label="Rules newly failing"
        value={delta.new_rule_ids.length ? delta.new_rule_ids.join(', ') : 'none'}
        tone={delta.new_rule_ids.length ? 'danger' : undefined}
      />
    </dl>
  )
}

function Measurement({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'danger'
}) {
  return (
    <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd
        className={`mt-0.5 font-medium ${
          tone === 'danger'
            ? 'text-red-700 dark:text-red-400'
            : 'text-slate-900 dark:text-slate-100'
        }`}
      >
        {value}
      </dd>
    </div>
  )
}

function VerdictItem({ finding }: { finding: FindingVerification }) {
  return (
    <li className="rounded-md border border-slate-200 p-3 text-sm dark:border-slate-800">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={verdictTone(finding.verdict)}>{finding.verdict}</Badge>
        <span className="font-medium text-slate-900 dark:text-slate-100">
          {finding.finding_title}
        </span>
      </div>
      <p className="mt-1 text-slate-600 dark:text-slate-400">{finding.explanation}</p>
    </li>
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

function verdictTone(verdict: FindingVerification['verdict']): BadgeTone {
  switch (verdict) {
    case 'resolved':
      return 'success'
    case 'unresolved':
      return 'danger'
    default:
      return 'neutral'
  }
}
