import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { DesignAnalysis, Project, VerificationResult } from '../lib/api'
import { VerificationSection } from './VerificationSection'

const PROJECT = { id: 'proj-1', target_url: 'https://example.com' } as Project

const APPLIED: DesignAnalysis = {
  id: 'run-1',
  verification: null,
  verification_screenshot_key: null,
  verification_target_url: null,
  verification_diff_image_key: null,
  production_screenshot_key: 'design-analyses/run-1/production.png',
  target_url: 'https://example.com',
  fix_application: {
    applied_at: '2026-01-04T00:00:00Z',
    fixes: [
      { finding_title: 'html-has-lang', file_path: 'index.html', applied: true, reason: null },
    ],
  },
} as DesignAnalysis

const RESULT: VerificationResult = {
  summary: 'The language attribute is now set.',
  findings: [
    {
      finding_title: 'html-has-lang',
      verdict: 'resolved',
      explanation: 'axe no longer reports the rule.',
    },
  ],
  regressions: [],
  accessibility_delta: {
    resolved_rule_ids: ['html-has-lang'],
    remaining_rule_ids: ['region'],
    new_rule_ids: [],
  },
  mismatch_percentage_before: 12.5,
  mismatch_percentage_after: 9.25,
  production_changed: true,
}

describe('VerificationSection', () => {
  it('stays hidden until a patch was actually written to a file', () => {
    const skipped: DesignAnalysis = {
      ...APPLIED,
      fix_application: {
        applied_at: '2026-01-04T00:00:00Z',
        fixes: [
          {
            finding_title: 'html-has-lang',
            file_path: 'index.html',
            applied: false,
            reason: 'the code is no longer in the file',
            backup_path: null,
          },
        ],
      },
    }

    const { container } = render(
      <VerificationSection project={PROJECT} analysis={skipped} onVerify={vi.fn()} onApply={vi.fn()} />,
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('verifies against a URL override when one is given', async () => {
    const onVerify = vi.fn().mockResolvedValue(undefined)
    render(<VerificationSection project={PROJECT} analysis={APPLIED} onVerify={onVerify} onApply={vi.fn()} />)

    fireEvent.change(screen.getByLabelText(/url to verify against/i), {
      target: { value: 'http://localhost:4321' },
    })
    fireEvent.click(screen.getByRole('button', { name: /verify fixes/i }))

    expect(onVerify).toHaveBeenCalledWith('run-1', 'http://localhost:4321')
  })

  it('falls back to the project URL when the override is left blank', () => {
    const onVerify = vi.fn().mockResolvedValue(undefined)
    render(<VerificationSection project={PROJECT} analysis={APPLIED} onVerify={onVerify} onApply={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /verify fixes/i }))

    expect(onVerify).toHaveBeenCalledWith('run-1', undefined)
  })

  it('shows each verdict next to the measurement behind it', () => {
    render(
      <VerificationSection
        project={PROJECT}
        analysis={{
          ...APPLIED,
          verification: RESULT,
          verification_screenshot_key: 'design-analyses/run-1/verification/x-production.png',
        }}
        onVerify={vi.fn()}
        onApply={vi.fn()}
      />,
    )

    expect(screen.getByText('resolved')).toBeInTheDocument()
    expect(screen.getByText('12.50% → 9.25%')).toBeInTheDocument()
    // The before/after pair is the deliverable of this whole step.
    expect(screen.getByAltText(/before the fixes/i)).toBeInTheDocument()
    expect(screen.getByAltText(/after the fixes/i)).toBeInTheDocument()
  })

  it('says which two URLs were compared', () => {
    render(
      <VerificationSection
        project={PROJECT}
        analysis={{
          ...APPLIED,
          verification: RESULT,
          verification_target_url: 'http://localhost:8080/',
        }}
        onVerify={vi.fn()}
        onApply={vi.fn()}
      />,
    )

    // A local server standing in for the deployed site is allowed, so the
    // reader has to be able to see that's what happened.
    expect(screen.getByText('http://localhost:8080/')).toBeInTheDocument()
    expect(screen.getByText('https://example.com')).toBeInTheDocument()
  })

  it('says plainly when the page never changed, rather than reading it as a failed fix', () => {
    render(
      <VerificationSection
        project={PROJECT}
        analysis={{
          ...APPLIED,
          verification: { ...RESULT, production_changed: false, findings: [] },
        }}
        onVerify={vi.fn()}
        onApply={vi.fn()}
      />,
    )

    expect(screen.getByText(/did not change at all/i)).toBeInTheDocument()
  })

  it('calls out a rule that started failing after the change', () => {
    render(
      <VerificationSection
        project={PROJECT}
        analysis={{
          ...APPLIED,
          verification: {
            ...RESULT,
            accessibility_delta: { ...RESULT.accessibility_delta, new_rule_ids: ['color-contrast'] },
            regressions: ['The hero button lost its focus ring.'],
          },
        }}
        onVerify={vi.fn()}
        onApply={vi.fn()}
      />,
    )

    expect(screen.getByText('color-contrast')).toBeInTheDocument()
    expect(screen.getByText(/lost its focus ring/i)).toBeInTheDocument()
  })

  it('offers to re-apply the patches when a fix did not land', async () => {
    const onApply = vi.fn().mockResolvedValue(undefined)
    render(
      <VerificationSection
        project={PROJECT}
        analysis={{
          ...APPLIED,
          verification: {
            ...RESULT,
            findings: [
              {
                finding_title: 'html-has-lang',
                verdict: 'unresolved',
                explanation: 'axe still reports the rule.',
              },
            ],
          },
        }}
        onVerify={vi.fn()}
        onApply={onApply}
      />,
    )

    // The honest next move: the file may have been reverted or rebuilt,
    // so write the approved patches again and re-check.
    fireEvent.click(screen.getByRole('button', { name: /re-apply the patches/i }))

    expect(onApply).toHaveBeenCalledWith('run-1')
  })

  it('does not offer to re-apply once everything is resolved', () => {
    render(
      <VerificationSection
        project={PROJECT}
        analysis={{ ...APPLIED, verification: RESULT }}
        onVerify={vi.fn()}
        onApply={vi.fn()}
      />,
    )

    expect(
      screen.queryByRole('button', { name: /re-apply the patches/i }),
    ).not.toBeInTheDocument()
  })

  it('surfaces a failed verification run', async () => {
    const onVerify = vi.fn().mockRejectedValue(new Error("this run's patches haven't been applied"))
    render(<VerificationSection project={PROJECT} analysis={APPLIED} onVerify={onVerify} onApply={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /verify fixes/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent("haven't been applied")
  })
})
