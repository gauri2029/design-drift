import type { AggregatedFinding, DesignAnalysis, FindingPriority } from './api'

/** One row per problem, assembled from the six records the backend keeps
 * about it.
 *
 * The workflow produces findings, source locations, proposed patches,
 * review decisions, write results and verification verdicts as six parallel
 * lists joined only by `finding_title`. Rendering them as six sections —
 * which is what the app did — makes one problem look like six and leaves
 * the reader to do the join by eye. Doing it here once is what lets the UI
 * show a problem as a single thing with a single state.
 */

/** Severity in the user's words.
 *
 * The backend speaks three dialects at once: `priority` (high/medium/low),
 * `original_severity` (each agent's own word — "critical", "serious",
 * "cosmetic"), and axe's impact scale. Showing all three made a list of
 * findings read like a taxonomy exercise. */
export const SEVERITY: Record<FindingPriority, { label: string; rank: number }> = {
  high: { label: 'Blocking', rank: 0 },
  medium: { label: 'Worth fixing', rank: 1 },
  low: { label: 'Minor', rank: 2 },
}

/** Approving a patch and writing it to disk are different events, and the
 * old UI ran them together — a run could show "approved" while the file was
 * untouched, or "not applied" when the change was already there. */
export type FixState =
  | 'no-fix'
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'applied'
  | 'already-present'
  | 'manual'
  | 'verified'
  | 'unresolved'

export const FIX_STATE: Record<
  FixState,
  { label: string; tone: 'neutral' | 'ok' | 'warn' | 'bad' | 'accent' | 'info' }
> = {
  'no-fix': { label: 'Needs a decision', tone: 'neutral' },
  pending: { label: 'Ready to review', tone: 'accent' },
  approved: { label: 'Approved', tone: 'accent' },
  rejected: { label: 'Skipped', tone: 'neutral' },
  applied: { label: 'Written — not verified', tone: 'info' },
  'already-present': { label: 'Already fixed', tone: 'ok' },
  manual: { label: 'Fix by hand', tone: 'warn' },
  verified: { label: 'Fixed', tone: 'ok' },
  unresolved: { label: 'Didn’t work', tone: 'bad' },
}

type Location = NonNullable<DesignAnalysis['code_analysis']>['locations'][number]
type Fix = NonNullable<DesignAnalysis['fix_proposal']>['fixes'][number]

export interface Issue {
  finding: AggregatedFinding
  location: Location | null
  fix: Fix | null
  state: FixState
  /** Where the pre-patch file was saved, when something was written. */
  backupPath: string | null
  /** Why the verification agent reached its verdict. Null until verified. */
  verdictNote: string | null
}

/** Axe rule ids are written for the spec, not for a reader.
 *
 * "html-has-lang" tells a designer nothing, and this is the one place the
 * app can translate without inventing: the mapping is a fixed table, and an
 * unmapped id falls through to the raw title rather than to a guess. The id
 * itself stays visible once a row is open, because it is the search term
 * when you want to read the actual rule. */
const RULE_HEADLINES: Record<string, string> = {
  'html-has-lang': 'The page doesn’t say what language it’s in',
  'html-lang-valid': 'The page’s language code isn’t valid',
  'image-alt': 'An image has no alt text',
  'input-image-alt': 'An image button has no alt text',
  'area-alt': 'An image map area has no alt text',
  'color-contrast': 'Text is too faint to read against its background',
  'link-name': 'A link has no readable text',
  'button-name': 'A button has no readable text',
  label: 'A form field has no label',
  'form-field-multiple-labels': 'A form field has conflicting labels',
  'document-title': 'The page has no title',
  'landmark-one-main': 'The page has no main landmark',
  region: 'Some content sits outside any landmark',
  'page-has-heading-one': 'The page has no top-level heading',
  'heading-order': 'Heading levels skip a step',
  'duplicate-id': 'Two elements share the same id',
  'duplicate-id-active': 'Two interactive elements share the same id',
  'duplicate-id-aria': 'Two elements referenced by ARIA share the same id',
  'aria-allowed-attr': 'An ARIA attribute isn’t allowed on this element',
  'aria-required-attr': 'An ARIA role is missing a required attribute',
  'aria-valid-attr-value': 'An ARIA attribute has an invalid value',
  'aria-hidden-focus': 'A hidden element can still be focused',
  list: 'A list contains items that aren’t list items',
  listitem: 'A list item sits outside a list',
  'meta-viewport': 'Zooming is turned off on this page',
  tabindex: 'A positive tabindex overrides the natural tab order',
  'frame-title': 'An embedded frame has no title',
  bypass: 'There’s no way to skip to the main content',
}

/** What a row says before you open it. Visual findings already carry a
 * sentence written by the model, so they pass through untouched. */
export function issueHeadline(issue: Pick<Issue, 'finding'>): string {
  if (issue.finding.source !== 'accessibility') return issue.finding.title
  return RULE_HEADLINES[issue.finding.title] ?? issue.finding.title
}

export function buildIssues(analysis: DesignAnalysis): Issue[] {
  const locations = analysis.code_analysis?.locations ?? []
  const fixes = analysis.fix_proposal?.fixes ?? []
  const decisions = analysis.fix_review?.decisions ?? []
  const writes = analysis.fix_application?.fixes ?? []
  const verdicts = analysis.verification?.findings ?? []

  return (analysis.aggregated_findings?.findings ?? [])
    .map<Issue>((finding) => {
      const location = locations.find((l) => l.finding_title === finding.title) ?? null
      const fix = fixes.find((f) => f.finding_title === finding.title) ?? null
      const decision = decisions.find((d) => d.finding_title === finding.title)?.decision ?? null
      const write = writes.find((w) => w.finding_title === finding.title) ?? null
      const verification = verdicts.find((v) => v.finding_title === finding.title) ?? null
      // Widened deliberately: the union type makes the 'resolved' check look
      // unreachable to the narrower, though the value is runtime data.
      const verdict: string | null = verification?.verdict ?? null

      return {
        finding,
        location,
        fix,
        backupPath: write?.backup_path ?? null,
        verdictNote: verification?.explanation ?? null,
        state: resolve(),
      }

      // Later facts override earlier ones: a patch that has been verified
      // tells you strictly more than one that was merely approved.
      function resolve(): FixState {
        if (verdict === 'resolved') return 'verified'
        if (verdict !== null) return 'unresolved'
        if (write?.applied) return 'applied'
        // The backend's own wording for a change that was already there —
        // a real outcome, not a failure to apply.
        if (write?.reason?.includes('already in the file')) return 'already-present'
        if (write) return 'manual'
        if (decision === 'rejected') return 'rejected'
        if (decision === 'approved') return 'approved'
        if (!fix) return location && !location.no_match ? 'no-fix' : 'manual'
        if (fix.no_fix || !fix.patch) return 'manual'
        return 'pending'
      }
    })
    .sort((a, b) => SEVERITY[a.finding.priority].rank - SEVERITY[b.finding.priority].rank)
}

export function summarise(issues: Issue[]) {
  return {
    total: issues.length,
    blocking: issues.filter((i) => i.finding.priority === 'high').length,
    located: issues.filter((i) => i.location && !i.location.no_match).length,
    pending: issues.filter((i) => i.state === 'pending').length,
    approved: issues.filter((i) => i.state === 'approved').length,
    fixed: issues.filter((i) => i.state === 'verified' || i.state === 'already-present').length,
    written: issues.filter((i) => i.state === 'applied').length,
  }
}

/** The headline sentence for a finished run.
 *
 * A number alone ("7 findings", "3.42% mismatch") asks the reader to supply
 * the judgement. This writes the sentence they would otherwise compose, and
 * splits the count out so the UI can roll it up independently of the words
 * around it. */
export function verdict(issues: Issue[]): {
  headline: string
  detail: string
  count: number | null
  after: string
} {
  const counts = summarise(issues)

  if (counts.total === 0) {
    return {
      headline: 'This page matches its design',
      detail: 'Nothing needs your attention on this run.',
      count: null,
      after: 'This page matches its design',
    }
  }

  const accessibility = issues.filter((i) => i.finding.source === 'accessibility').length
  const visual = counts.total - accessibility
  const parts = [
    visual > 0 && `${visual} visual ${visual === 1 ? 'difference' : 'differences'}`,
    accessibility > 0 &&
      `${accessibility} accessibility ${accessibility === 1 ? 'issue' : 'issues'}`,
  ].filter(Boolean)

  const blocking = counts.blocking > 0
  const after = blocking
    ? ` ${counts.blocking === 1 ? 'thing needs' : 'things need'} fixing before you ship`
    : 'This page has drifted from its design'

  return {
    headline: blocking ? `${counts.blocking}${after}` : after,
    detail: `Found ${parts.join(' and ')}.`,
    count: blocking ? counts.blocking : null,
    after,
  }
}
