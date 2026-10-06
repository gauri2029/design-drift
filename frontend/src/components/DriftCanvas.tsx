import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  type WheelEvent,
} from 'react'
import { Button } from './ui'

export type CanvasMode = 'reveal' | 'split' | 'diff'

/** The drift canvas: the design and the live page staged as one object.
 *
 * This is the app's centre of gravity. Every other view answers a question
 * about the work; this one *is* the work. So it gets the room — one large
 * stage with the comparison filling it, and every control floating over it
 * in glass rather than boxed beside it.
 *
 * Reveal is the default because a hard edge between two images asks the eye
 * only "does this line continue?", which it answers involuntarily. A blend
 * slider asks you to interpret a translucent double-image instead. Split is
 * for reading two long pages together; diff for the computed mismatch map.
 */
export function DriftCanvas({
  designSrc,
  productionSrc,
  diffSrc,
  mismatch,
  mode,
  onModeChange,
}: {
  designSrc: string
  productionSrc: string
  diffSrc?: string
  mismatch?: number
  mode: CanvasMode
  onModeChange: (mode: CanvasMode) => void
}) {
  const [zoom, setZoom] = useState(1)
  const [reveal, setReveal] = useState(50)
  const stage = useRef<HTMLDivElement>(null)
  const leftPane = useRef<HTMLDivElement>(null)
  const rightPane = useRef<HTMLDivElement>(null)
  const syncing = useRef(false)
  const [dragging, setDragging] = useState(false)

  const moveDivider = useCallback((clientX: number) => {
    const box = stage.current?.getBoundingClientRect()
    if (!box || box.width === 0) return
    setReveal(clamp(((clientX - box.left) / box.width) * 100, 0, 100))
  }, [])

  // Pointer listeners go on the window, not the handle: mid-drag the cursor
  // routinely outruns a thin target, and losing the drag there is the single
  // most irritating way for this control to fail.
  useEffect(() => {
    if (!dragging) return
    const move = (event: PointerEvent) => moveDivider(event.clientX)
    const stop = () => setDragging(false)
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
    window.addEventListener('pointercancel', stop)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
      window.removeEventListener('pointercancel', stop)
    }
  }, [dragging, moveDivider])

  // Ctrl/Cmd+wheel zooms, as in every design tool; a plain wheel still
  // scrolls so the stage never traps the page.
  const onWheel = (event: WheelEvent) => {
    if (!event.ctrlKey && !event.metaKey) return
    event.preventDefault()
    setZoom((current) => clamp(current - event.deltaY * 0.002, 0.25, 4))
  }

  const sync = (from: HTMLDivElement | null, to: HTMLDivElement | null) => {
    if (!from || !to || syncing.current) return
    syncing.current = true
    to.scrollTop = from.scrollTop
    to.scrollLeft = from.scrollLeft
    requestAnimationFrame(() => {
      syncing.current = false
    })
  }

  const modes: { id: CanvasMode; label: string; enabled: boolean }[] = [
    { id: 'reveal', label: 'Reveal', enabled: true },
    { id: 'split', label: 'Split', enabled: true },
    { id: 'diff', label: 'Diff', enabled: Boolean(diffSrc) },
  ]

  return (
    <div className="relative">
      {/* Floating controls. Glass earns its keep here specifically: the bar
          sits over the imagery it controls, and you can see the work
          continue underneath it. */}
      <div className="glass absolute left-1/2 top-4 z-30 flex -translate-x-1/2 items-center gap-1 rounded-2xl px-1.5 py-1.5">
        {modes.map((candidate) => (
          <button
            key={candidate.id}
            type="button"
            disabled={!candidate.enabled}
            aria-pressed={mode === candidate.id}
            onClick={() => onModeChange(candidate.id)}
            className={`tilt rounded-xl px-3.5 py-1.5 text-[13px] font-medium transition-colors duration-200 disabled:opacity-25 ${
              mode === candidate.id
                ? 'bg-accent text-accent-ink shadow-[0_4px_16px_-4px_var(--color-violet)]'
                : 'text-ink-dim hover:bg-tint-hi hover:text-ink'
            }`}
          >
            {candidate.label}
          </button>
        ))}

        <span className="mx-1 h-5 w-px bg-edge-hi" aria-hidden="true" />

        <Button
          size="sm"
          variant="ghost"
          aria-label="Zoom out"
          onClick={() => setZoom((z) => clamp(z - 0.25, 0.25, 4))}
        >
          −
        </Button>
        <span className="w-11 text-center font-mono text-[11px] tabular-nums text-ink-dim">
          {Math.round(zoom * 100)}%
        </span>
        <Button
          size="sm"
          variant="ghost"
          aria-label="Zoom in"
          onClick={() => setZoom((z) => clamp(z + 0.25, 0.25, 4))}
        >
          +
        </Button>
        {zoom !== 1 && (
          <Button size="sm" variant="ghost" onClick={() => setZoom(1)}>
            Reset
          </Button>
        )}
      </div>

      <div className="overflow-hidden rounded-3xl border border-edge bg-void shadow-[0_24px_70px_-20px_var(--glass-shadow)]">
        {mode === 'reveal' && (
          <div
            ref={stage}
            onWheel={onWheel}
            tabIndex={0}
            role="group"
            aria-label="Design and live page comparison. Scroll to pan."
            className="relative max-h-[58vh] overflow-auto"
          >
            {/* Pinned to the stage rather than the image: a label that
                scrolls away with the content stops naming anything. */}
            <SideLabel className="left-4">Design</SideLabel>
            <SideLabel className="right-4">Live</SideLabel>
            <div
              className={`relative select-none ${dragging ? 'cursor-ew-resize' : ''}`}
              style={{ width: `${zoom * 100}%` }}
            >
              <img src={designSrc} alt="The design" className="block w-full" draggable={false} />
              <div
                className="absolute inset-0 overflow-hidden"
                style={{ clipPath: `inset(0 0 0 ${reveal}%)` }}
              >
                <img
                  src={productionSrc}
                  alt="The live page, revealed to the right of the divider"
                  className="block w-full"
                  draggable={false}
                />
              </div>
              <Divider reveal={reveal} onGrab={() => setDragging(true)} dragging={dragging} />
            </div>
          </div>
        )}

        {mode === 'split' && (
          <div className="grid gap-px bg-edge md:grid-cols-2">
            <Pane
              paneRef={leftPane}
              label="Design"
              src={designSrc}
              zoom={zoom}
              onScroll={() => sync(leftPane.current, rightPane.current)}
              onWheel={onWheel}
            />
            <Pane
              paneRef={rightPane}
              label="Live"
              src={productionSrc}
              zoom={zoom}
              onScroll={() => sync(rightPane.current, leftPane.current)}
              onWheel={onWheel}
            />
          </div>
        )}

        {mode === 'diff' && diffSrc && (
          <div
            onWheel={onWheel}
            tabIndex={0}
            role="group"
            aria-label="Map of differing pixels. Scroll to pan."
            className="relative max-h-[58vh] overflow-auto"
          >
            <SideLabel className="left-4">Differences</SideLabel>
            <img
              src={diffSrc}
              alt="Every pixel that differs between the design and the live page"
              className="block"
              style={{ width: `${zoom * 100}%` }}
            />
          </div>
        )}
      </div>

      {mismatch !== undefined && (
        <p className="mt-3 text-center text-[13px] text-ink-faint">
          <span className="font-mono tabular-nums text-ink-dim">{mismatch.toFixed(2)}%</span> of
          pixels differ — a diagnostic signal, not a score. One shifted element or a different page
          height can dominate it.
        </p>
      )}
    </div>
  )
}

/** The reveal divider: a lit seam with a grip you can grab anywhere. */
function Divider({
  reveal,
  onGrab,
  dragging,
}: {
  reveal: number
  onGrab: () => void
  dragging: boolean
}) {
  return (
    <>
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 z-10 w-px bg-accent shadow-[0_0_20px_2px_var(--color-violet)]"
        style={{ left: `${reveal}%` }}
      />
      <div
        className="absolute inset-y-0 z-20 flex w-10 -translate-x-1/2 cursor-ew-resize touch-none items-start justify-center"
        style={{ left: `${reveal}%` }}
        onPointerDown={(event: ReactPointerEvent) => {
          event.preventDefault()
          onGrab()
        }}
      >
        <span
          className={`glass sticky top-24 grid h-10 w-10 place-items-center rounded-full text-ink transition-transform duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
            dragging ? 'scale-110 rotate-180' : 'hover:scale-110'
          }`}
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden="true">
            <path
              d="M9 7 5 12l4 5M15 7l4 5-4 5"
              stroke="currentColor"
              strokeWidth="1.9"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </div>
    </>
  )
}

/** A caption pinned to the stage, over the imagery. */
function SideLabel({ className, children }: { className: string; children: ReactNode }) {
  return (
    <span
      className={`glass pointer-events-none absolute top-[4.5rem] z-20 rounded-full px-3 py-1 font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-ink-dim ${className}`}
    >
      {children}
    </span>
  )
}

function Pane({
  paneRef,
  label,
  src,
  zoom,
  onScroll,
  onWheel,
}: {
  paneRef: React.RefObject<HTMLDivElement | null>
  label: string
  src: string
  zoom: number
  onScroll: () => void
  onWheel: (event: WheelEvent) => void
}) {
  return (
    // The label is pinned to this wrapper rather than to the scrolling
    // element, or it travels up out of view with the image.
    <div className="relative bg-void">
      <SideLabel className="left-4">{label}</SideLabel>
      <div
        ref={paneRef}
        onScroll={onScroll}
        onWheel={onWheel}
        tabIndex={0}
        role="group"
        aria-label={`${label}. Scroll to pan — both panes move together.`}
        className="max-h-[58vh] overflow-auto"
      >
        <img src={src} alt={label} className="block" style={{ width: `${zoom * 100}%` }} />
      </div>
    </div>
  )
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}
