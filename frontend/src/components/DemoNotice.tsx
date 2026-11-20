import { useState } from 'react'
import { Button } from './ui'

/** What an anonymous visitor is told about the demo, up front.
 *
 * The honest framing matters more than the styling here. Everything on
 * screen - the findings, the located files, the patches, the verification
 * verdict - came out of a real run of the agents against a real deployed
 * site. What is switched off is *starting another one*, because a run opens
 * a browser and calls a model, and a public URL that lets anyone do that
 * spends the author's API budget on whoever finds it.
 *
 * So this says both halves: the results are real, the execution is locked.
 * Claiming the first without admitting the second would be the kind of
 * demo docs/principles.md #2 exists to rule out.
 */
export function DemoNotice({ ownerName }: { ownerName: string | null }) {
  const [open, setOpen] = useState(false)

  return (
    <section
      aria-labelledby="demo-notice-title"
      className="glass animate-rise mb-6 rounded-3xl border border-accent/25 p-5 sm:p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-accent">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
              Live demo
            </span>
            <span className="text-[13px] text-ink-faint">
              {ownerName ? `${ownerName}'s project` : 'no sign-up needed'}
            </span>
          </p>

          <h2
            id="demo-notice-title"
            className="font-display mt-3 text-[19px] font-bold leading-snug text-ink sm:text-[21px]"
          >
            A real agent run, saved so you can read it
          </h2>

          <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-ink-dim">
            Every finding, source location, proposed patch and verification verdict
            below was produced by the agents running against a live deployed site.
            Nothing here is mocked. What is turned off is starting a{' '}
            <em className="not-italic text-ink">new</em> run: that opens a real
            browser and calls a model, so it stays off on a public URL.
          </p>
        </div>

        <Button
          size="sm"
          variant="ghost"
          onClick={() => setOpen((previous) => !previous)}
          aria-expanded={open}
        >
          {open ? 'Hide detail' : 'What is real?'}
        </Button>
      </div>

      {open && (
        <dl className="animate-rise mt-5 grid gap-4 border-t border-edge pt-5 sm:grid-cols-2">
          <div>
            <dt className="text-[12px] font-semibold uppercase tracking-[0.07em] text-ok">
              Real, and stored from a genuine run
            </dt>
            <dd className="mt-2 text-[13px] leading-relaxed text-ink-dim">
              The Figma render and the page screenshot, the pixel diff, the
              axe-core accessibility report, the triaged findings, the files and
              line numbers the Code Analysis agent matched, the patches the Fix
              agent drafted, and the verdict after the fix landed.
            </dd>
          </div>
          <div>
            <dt className="text-[12px] font-semibold uppercase tracking-[0.07em] text-warn">
              Disabled on this public URL
            </dt>
            <dd className="mt-2 text-[13px] leading-relaxed text-ink-dim">
              Running the workflow again, re-running a scan or an AI review,
              approving or applying a patch, verifying, and deleting the project.
              Each is refused by the API itself, not just hidden here. Sign up to
              point the agents at your own Figma frame and page.
            </dd>
          </div>
        </dl>
      )}
    </section>
  )
}
