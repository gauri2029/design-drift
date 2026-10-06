import { describe, expect, it } from 'vitest'
import type { DesignAnalysis } from './api'
import { buildIssues, issueHeadline, summarise, verdict } from './issues'
import { parseFigmaUrl } from './figmaUrl'

/** A run with one finding, plus whatever later records a test needs. */
function analysis(overrides: Partial<DesignAnalysis> = {}): DesignAnalysis {
  return {
    id: 'run-1',
    project_id: 'proj-1',
    model: 'gemini-2.5-flash',
    result: { layout_summary: '', design_intent: '', key_components: [], implementation_risks: [] },
    production_screenshot_key: 'p',
    target_url: 'https://example.com',
    comparison_result: null,
    diff_image_key: 'd',
    visual_comparison: null,
    accessibility_report: null,
    accessibility_interpretation: null,
    aggregated_findings: {
      problems_found: true,
      findings: [
        {
          source: 'accessibility',
          priority: 'high',
          original_severity: 'serious',
          title: 'html-has-lang',
          detail: 'No lang attribute.',
          likely_area: null,
        },
      ],
    },
    code_analysis: null,
    fix_proposal: null,
    fix_review: null,
    fix_application: null,
    verification: null,
    verification_screenshot_key: null,
    verification_diff_image_key: null,
    verification_target_url: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  } as DesignAnalysis
}

const PATCH = {
  finding_title: 'html-has-lang',
  no_fix: false,
  patch: {
    file_path: 'index.html',
    line_start: 2,
    line_end: 2,
    original_code: '<html>',
    replacement_code: '<html lang="en">',
  },
  explanation: 'Declares the language.',
  confidence: 'high' as const,
  original_code_found: true,
}

describe('buildIssues', () => {
  it('joins the per-finding records into one row', () => {
    const [issue] = buildIssues(
      analysis({
        code_analysis: {
          summary: '',
          locations: [
            {
              finding_title: 'html-has-lang',
              no_match: false,
              location: {
                file_path: 'index.html',
                line_start: 2,
                line_end: 2,
                code_evidence: '<html>',
              },
              explanation: 'The document element.',
              confidence: 'high',
            },
          ],
        },
        fix_proposal: { summary: '', fixes: [PATCH] },
      }),
    )

    // Findings, locations and fixes were three separate sections that you
    // matched up by title yourself.
    expect(issue.location?.location?.file_path).toBe('index.html')
    expect(issue.fix?.patch?.replacement_code).toBe('<html lang="en">')
    expect(issue.state).toBe('pending')
  })

  describe('fix state', () => {
    it('separates approving from writing to a file', () => {
      const approved = buildIssues(
        analysis({
          fix_proposal: { summary: '', fixes: [PATCH] },
          fix_review: {
            reviewed_at: '2026-01-02T00:00:00Z',
            decisions: [{ finding_title: 'html-has-lang', decision: 'approved' }],
          },
        }),
      )
      // Approving records a decision; applying edits a file. Conflating
      // them was the old UI's worst ambiguity.
      expect(approved[0].state).toBe('approved')

      const written = buildIssues(
        analysis({
          fix_proposal: { summary: '', fixes: [PATCH] },
          fix_application: {
            applied_at: '2026-01-02T00:00:00Z',
            fixes: [
              {
                finding_title: 'html-has-lang',
                file_path: 'index.html',
                applied: true,
                reason: null,
                backup_path: '.design-drift-backups/x/index.html',
              },
            ],
          },
        }),
      )
      expect(written[0].state).toBe('applied')
      expect(written[0].backupPath).toBe('.design-drift-backups/x/index.html')
    })

    it('reads a change already in the file as its own outcome', () => {
      const [issue] = buildIssues(
        analysis({
          fix_proposal: { summary: '', fixes: [PATCH] },
          fix_application: {
            applied_at: '2026-01-02T00:00:00Z',
            fixes: [
              {
                finding_title: 'html-has-lang',
                file_path: 'index.html',
                applied: false,
                reason: 'this change is already in the file',
                backup_path: null,
              },
            ],
          },
        }),
      )

      // Not a failure: the work is done. Showing it as "not applied" made
      // a succeeded re-apply look broken.
      expect(issue.state).toBe('already-present')
    })

    it('calls a finding with no possible patch a manual change', () => {
      const [issue] = buildIssues(
        analysis({
          fix_proposal: {
            summary: '',
            fixes: [
              {
                finding_title: 'html-has-lang',
                no_fix: true,
                patch: null,
                explanation: 'The right content exists only in the design.',
                confidence: 'low',
                original_code_found: false,
              },
            ],
          },
        }),
      )

      expect(issue.state).toBe('manual')
    })

    it('lets a verification verdict override everything before it', () => {
      const base = {
        fix_proposal: { summary: '', fixes: [PATCH] },
        fix_application: {
          applied_at: '2026-01-02T00:00:00Z',
          fixes: [
            {
              finding_title: 'html-has-lang',
              file_path: 'index.html',
              applied: true,
              reason: null,
              backup_path: null,
            },
          ],
        },
      }
      const verification = {
        summary: '',
        regressions: [],
        accessibility_delta: { resolved_rule_ids: [], remaining_rule_ids: [], new_rule_ids: [] },
        mismatch_percentage_before: 1,
        mismatch_percentage_after: 1,
        production_changed: true,
      }

      const resolved = buildIssues(
        analysis({
          ...base,
          verification: {
            ...verification,
            findings: [
              { finding_title: 'html-has-lang', verdict: 'resolved', explanation: 'Now present.' },
            ],
          },
        }),
      )
      expect(resolved[0].state).toBe('verified')
      expect(resolved[0].verdictNote).toBe('Now present.')

      const failed = buildIssues(
        analysis({
          ...base,
          verification: {
            ...verification,
            findings: [{ finding_title: 'html-has-lang', verdict: 'unresolved', explanation: '' }],
          },
        }),
      )
      // A patch that landed but didn't work must not read as done.
      expect(failed[0].state).toBe('unresolved')
    })
  })

  it('orders blocking issues first', () => {
    const run = analysis()
    run.aggregated_findings!.findings.unshift({
      source: 'visual_comparison',
      priority: 'low',
      original_severity: 'cosmetic',
      title: 'Minor spacing',
      detail: '',
      likely_area: null,
    })

    expect(buildIssues(run).map((issue) => issue.finding.title)).toEqual([
      'html-has-lang',
      'Minor spacing',
    ])
  })
})

describe('issueHeadline', () => {
  it('translates an axe rule id into something a designer can read', () => {
    const [issue] = buildIssues(analysis())

    // "html-has-lang" is written for the spec, not for a reader. The raw
    // id stays visible inside the opened row.
    expect(issue.finding.title).toBe('html-has-lang')
    expect(issueHeadline(issue)).toBe('The page doesn’t say what language it’s in')
  })

  it('leaves a visual finding’s own wording alone', () => {
    const run = analysis()
    run.aggregated_findings!.findings = [
      {
        source: 'visual_comparison',
        priority: 'medium',
        original_severity: 'moderate',
        title: 'The hero heading sits 12px lower than the design',
        detail: '',
        likely_area: 'Hero',
      },
    ]

    // The model already wrote a sentence; rewriting it would lose detail.
    expect(issueHeadline(buildIssues(run)[0])).toBe(
      'The hero heading sits 12px lower than the design',
    )
  })

  it('falls back to the raw id for a rule it doesn’t know', () => {
    const run = analysis()
    run.aggregated_findings!.findings[0].title = 'some-new-axe-rule'

    // Better a term you can search for than a confident invention.
    expect(issueHeadline(buildIssues(run)[0])).toBe('some-new-axe-rule')
  })
})

describe('verdict', () => {
  it('writes the sentence a reader would otherwise have to compose', () => {
    const run = analysis()
    run.aggregated_findings!.findings.push({
      source: 'visual_comparison',
      priority: 'low',
      original_severity: 'cosmetic',
      title: 'Footer spacing',
      detail: '',
      likely_area: null,
    })

    const call = verdict(buildIssues(run))
    expect(call.headline).toBe('1 thing needs fixing before you ship')
    expect(call.detail).toBe('Found 1 visual difference and 1 accessibility issue.')
    // Split out so the count can roll up independently of the words.
    expect(call.count).toBe(1)
  })

  it('says so plainly when a page is clean', () => {
    const run = analysis()
    run.aggregated_findings!.findings = []

    const call = verdict(buildIssues(run))
    expect(call.headline).toBe('This page matches its design')
    // No number to animate when the headline carries no count.
    expect(call.count).toBeNull()
  })
})

describe('summarise', () => {
  it('counts what the header reports', () => {
    const counts = summarise(
      buildIssues(analysis({ fix_proposal: { summary: '', fixes: [PATCH] } })),
    )

    expect(counts).toMatchObject({ total: 1, blocking: 1, pending: 1, fixed: 0 })
  })
})

describe('parseFigmaUrl', () => {
  it('reads the file key and node id out of a frame link', () => {
    // Node ids are hyphenated in URLs and colon-separated in the API.
    expect(parseFigmaUrl('https://www.figma.com/design/6vJNrp/Site?node-id=94-2143')).toEqual({
      fileKey: '6vJNrp',
      nodeId: '94:2143',
    })
  })

  it('handles the older /file/ form and percent-encoded ids', () => {
    expect(parseFigmaUrl('https://figma.com/file/AbC123/Old?node-id=1%3A23')).toEqual({
      fileKey: 'AbC123',
      nodeId: '1:23',
    })
  })

  it('returns null rather than guessing', () => {
    // A file link with no frame selected can't say which node to compare.
    expect(parseFigmaUrl('https://figma.com/design/AbC123/Site')).toBeNull()
    expect(parseFigmaUrl('https://example.com/design/AbC123?node-id=1-2')).toBeNull()
    expect(parseFigmaUrl('not a url')).toBeNull()
  })
})
