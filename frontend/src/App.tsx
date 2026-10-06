import { ProjectsPanel } from './components/ProjectsPanel'
import { BrandMark, ThemeToggle } from './components/ui'

function App() {
  return (
    <div className="min-h-screen">
      {/* First in the tab order, visible only on focus: the rail is a long
          list and keyboard users shouldn't walk it on every visit. */}
      <a href="#workspace" className="skip-link">
        Skip to the workspace
      </a>

      {/* Drifting colour blobs and grain behind everything. Fixed and
          composited once, so the 26s animation is free. */}
      <div className="room" aria-hidden="true" />

      {/* Glass, because the work scrolls underneath it. The marketing copy
          that used to sit below — a headline and a paragraph explaining the
          product — is gone: it addressed someone deciding whether to use the
          tool, in the one place reserved for someone using it. The
          "Connected to backend" badge went for the same reason: a working
          backend is the normal case, and a broken one surfaces as an error
          where you tried to act. */}
      <header className="sticky top-0 z-40 border-b border-edge bg-void/50 backdrop-blur-2xl">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-3 px-6 py-3.5">
          <div className="flex items-center gap-2.5">
            <span className="text-accent">
              <BrandMark className="h-6 w-6" />
            </span>
            <span className="font-display text-[17px] font-bold tracking-[-0.02em] text-ink">
              Design Drift
            </span>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto max-w-[1600px] px-6 py-8 pe-7">
        <ProjectsPanel />
      </main>
    </div>
  )
}

export default App
