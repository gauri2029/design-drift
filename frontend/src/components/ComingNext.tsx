/** What is deliberately not built yet, and why.
 *
 * Placed at the end of the Fix view, where someone has just finished
 * reviewing patches and is about to export one - the exact moment the
 * question "why doesn't it just open the PR?" occurs to them.
 *
 * Phrased as a roadmap item rather than a feature, because it is one. The
 * current boundary is real: nothing in this codebase writes to git, and the
 * GitHub App's permission is Contents: read-only, so a push is impossible
 * rather than merely absent from the code (docs/principles.md #5).
 */
export function ComingNext() {
  return (
    <section
      aria-labelledby="coming-next-title"
      className="mt-8 rounded-3xl border border-dashed border-edge-hi bg-tint/40 p-5 sm:p-6"
    >
      <p className="inline-flex items-center gap-1.5 rounded-full border border-edge-hi bg-raised px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">
        Coming next
      </p>

      <h3
        id="coming-next-title"
        className="font-display mt-3 text-[17px] font-bold leading-snug text-ink"
      >
        Agent-generated GitHub pull requests
      </h3>

      <div className="mt-3 grid gap-5 sm:grid-cols-2">
        <div>
          <p className="text-[12px] font-semibold uppercase tracking-[0.07em] text-ink-faint">
            Today
          </p>
          <p className="mt-1.5 text-[13px] leading-relaxed text-ink-dim">
            You review each proposed patch, approve the ones you want, and export
            them as a unified diff. Applying it is your <code className="font-mono text-[12px] text-ink">git apply</code>,
            on your machine. Design Drift never commits or pushes, and its GitHub
            access is read-only by permission.
          </p>
        </div>
        <div>
          <p className="text-[12px] font-semibold uppercase tracking-[0.07em] text-accent">
            Next
          </p>
          <p className="mt-1.5 text-[13px] leading-relaxed text-ink-dim">
            The same approved patches, opened as a <em className="not-italic text-ink">draft</em>{' '}
            pull request on a branch for you to review in GitHub. Draft, on a
            branch, never to the default branch, and still only after the human
            approval step above. The review stays where the review belongs.
          </p>
        </div>
      </div>
    </section>
  )
}
