import { Button, BrandMark, Label, ThemeToggle } from './ui'
import { useCursorLight } from '../lib/motion'

const REPO_URL = 'https://github.com/gauri2029/design-drift'

/** What the product does, in the order it does it.
 *
 * Every step here maps to a real agent in backend/app/agents — nothing
 * aspirational. If a step is removed from the workflow it should come out
 * of this list too.
 */
const STEPS = [
  {
    title: 'Reads the design',
    body: 'Pulls the frame straight from Figma and works out what it was meant to look like - layout, components, and the parts most likely to be built wrong.',
  },
  {
    title: 'Opens the real page',
    body: 'Drives a real browser to your running app, captures it at several widths, and runs an accessibility audit against the live DOM.',
  },
  {
    title: 'Finds what drifted',
    body: 'Compares the two and reports the differences that matter, each one ranked by whether it should block a release.',
  },
  {
    title: 'Points at the code',
    body: 'Traces a finding back to the file and lines responsible, then proposes a patch you can read before anything is written.',
  },
  {
    title: 'Proves the fix worked',
    body: 'Re-captures the page after a change and says whether the issue is actually resolved - or whether something else broke.',
  },
]

const FACTS = [
  { value: 'Figma → live app', label: 'Compares' },
  { value: 'You approve', label: 'Every patch' },
  { value: 'Reversible', label: 'Edits are backed up' },
]

export function Landing({
  onGetStarted,
  onSignIn,
}: {
  onGetStarted: () => void
  onSignIn: () => void
}) {
  // The portfolio's cursor light, on the hero only — once per page is a
  // flourish, on every section it's noise.
  const hero = useCursorLight<HTMLDivElement>()

  return (
    <div className="min-h-screen">
      {/* Visually hidden until focused — see .skip-link in index.css. */}
      <a href="#what-it-does" className="skip-link">
        Skip to what it does
      </a>

      <header className="sticky top-0 z-40 border-b border-edge bg-void/50 backdrop-blur-2xl">
        <div className="mx-auto flex max-w-[1100px] items-center justify-between gap-3 px-6 py-3.5">
          <div className="flex items-center gap-2.5">
            <span className="text-accent">
              <BrandMark className="h-6 w-6" />
            </span>
            <span className="font-display text-[17px] font-bold tracking-[-0.02em] text-ink">
              Design Drift
            </span>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button variant="ghost" size="sm" onClick={onSignIn}>
              Sign in
            </Button>
            <Button variant="primary" size="sm" onClick={onGetStarted}>
              Get started
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1100px] px-6">
        {/* --- Hero --- */}
        <section
          onPointerMove={hero.onPointerMove}
          className="lit animate-rise pb-14 pt-20 text-center sm:pb-16 sm:pt-28"
        >
          <span className="inline-flex items-center gap-2 rounded-full border border-edge-hi bg-tint px-3.5 py-1.5 text-[12px] font-medium text-ink-dim">
            <span aria-hidden="true" className="text-accent">
              ◆
            </span>
            Design QA, run by agents
          </span>

          <h1 className="font-display mx-auto mt-7 max-w-[20ch] text-[clamp(2.4rem,7vw,4.1rem)] font-bold leading-[1.04] tracking-[-0.04em] text-ink">
            Find where your app <span className="gradient-text">drifted</span> from its design
          </h1>

          <p className="mx-auto mt-6 max-w-[54ch] text-[17px] leading-relaxed text-ink-dim">
            Design Drift compares a Figma frame against the page you actually shipped, explains
            every difference in plain language, and traces it back to the line of code that caused
            it.
          </p>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Button variant="primary" size="lg" onClick={onGetStarted}>
              Get started
            </Button>
            <Button variant="secondary" size="lg" onClick={onSignIn}>
              Sign in
            </Button>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noreferrer"
              className="tilt inline-flex items-center gap-2 rounded-2xl border border-edge-hi px-5 py-2.5 text-[15px] text-ink-dim transition-colors duration-200 hover:border-edge-hi hover:bg-tint hover:text-ink"
            >
              <svg viewBox="0 0 16 16" aria-hidden="true" className="h-4 w-4" fill="currentColor">
                <path d="M8 0a8 8 0 0 0-2.53 15.59c.4.07.55-.17.55-.38v-1.34c-2.23.49-2.7-1.07-2.7-1.07-.36-.93-.89-1.18-.89-1.18-.73-.5.05-.49.05-.49.8.06 1.23.83 1.23.83.72 1.23 1.88.87 2.34.67.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.03 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.14.46.55.38A8 8 0 0 0 8 0Z" />
              </svg>
              View on GitHub
            </a>
          </div>

          <dl className="mt-16 grid gap-px overflow-hidden rounded-2xl border border-edge sm:grid-cols-3">
            {FACTS.map((fact) => (
              <div key={fact.label} className="bg-raised px-5 py-5">
                <dt className="font-display text-[19px] font-bold tracking-[-0.02em] text-ink">
                  {fact.value}
                </dt>
                <dd className="mt-0.5 text-[13px] text-ink-faint">{fact.label}</dd>
              </div>
            ))}
          </dl>
        </section>

        {/* --- How it works --- */}
        <section id="what-it-does" className="border-t border-edge py-20 sm:py-24">
          <Label>How it works</Label>
          <h2 className="font-display mt-3 max-w-[24ch] text-[clamp(1.75rem,4vw,2.5rem)] font-bold leading-tight tracking-[-0.03em] text-ink">
            Five passes over one page
          </h2>
          <p className="mt-4 max-w-[58ch] text-[15px] leading-relaxed text-ink-dim">
            Each step is a separate agent with a narrow job, so you can see which one found a
            problem and why - not a single score you have to trust.
          </p>

          <ol className="mt-12 space-y-3">
            {STEPS.map((step, index) => (
              <li
                key={step.title}
                className="tilt group flex gap-5 rounded-2xl border border-edge bg-raised p-5 transition-colors duration-200 hover:border-edge-hi sm:p-6"
              >
                <span
                  aria-hidden="true"
                  className="font-mono text-[13px] font-medium text-accent-hi/70 transition-colors duration-200 group-hover:text-accent-hi"
                >
                  {String(index + 1).padStart(2, '0')}
                </span>
                <div className="min-w-0">
                  <h3 className="font-display text-[17px] font-semibold tracking-[-0.01em] text-ink">
                    {step.title}
                  </h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink-dim">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* --- The safeguard, stated plainly: it's the differentiator, not
            fine print. An agent that edits your source is only acceptable
            if you know exactly where the boundary is. --- */}
        <section className="border-t border-edge py-20 sm:py-24">
          <div className="glass rounded-3xl p-7 sm:p-10">
            <Label>Nothing happens without you</Label>
            <h2 className="font-display mt-3 max-w-[26ch] text-[clamp(1.6rem,3.5vw,2.2rem)] font-bold leading-tight tracking-[-0.03em] text-ink">
              It proposes. You decide.
            </h2>
            <p className="mt-4 max-w-[58ch] text-[15px] leading-relaxed text-ink-dim">
              Every patch is shown as a diff against your real file and waits for your approval.
              Applying one writes a backup first, and nothing ever touches your git history - no
              commits, no branches, no pushes.
            </p>
          </div>
        </section>
      </main>

      <footer className="border-t border-edge">
        <div className="mx-auto flex max-w-[1100px] flex-wrap items-center justify-between gap-4 px-6 py-8">
          <span className="text-[13px] text-ink-faint">
            Design Drift - an AI design QA workspace.
          </span>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="text-[13px] text-ink-dim transition-colors duration-200 hover:text-ink"
          >
            Source on GitHub
          </a>
        </div>
      </footer>
    </div>
  )
}
