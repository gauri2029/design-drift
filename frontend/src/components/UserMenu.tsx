import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { User } from '../lib/auth'

/** The account menu: a person icon that opens a small overlay.
 *
 * Rendered through a portal and positioned `fixed`, so the panel is
 * outside the header's layout entirely. An absolutely-positioned child
 * still participates in its ancestors' stacking and overflow, and in a
 * flex header that was enough to stretch the bar from 67px to 228px when
 * the menu opened. Nothing inside the header changes size now.
 */
export function UserMenu({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const [open, setOpen] = useState(false)
  const [anchor, setAnchor] = useState<{ top: number; right: number } | null>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)

  // Measured from the trigger rather than assumed, so the panel stays put
  // whatever the header's padding is at this breakpoint.
  const place = () => {
    const box = trigger.current?.getBoundingClientRect()
    if (box) setAnchor({ top: box.bottom + 8, right: window.innerWidth - box.right })
  }

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (trigger.current?.contains(target) || panel.current?.contains(target)) return
      setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        trigger.current?.focus()
      }
    }
    // Scrolling or resizing moves the trigger; the panel is fixed, so it
    // would otherwise detach and float on its own.
    const reposition = () => place()
    window.addEventListener('pointerdown', onPointerDown)
    window.addEventListener('keydown', onKey)
    window.addEventListener('resize', reposition)
    window.addEventListener('scroll', reposition, true)
    return () => {
      window.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', reposition)
      window.removeEventListener('scroll', reposition, true)
    }
  }, [open])

  const initial = (user.name || user.email).trim().charAt(0).toUpperCase()

  return (
    <>
      <button
        ref={trigger}
        type="button"
        onClick={() => {
          // Measured from the event's own target, after the browser has
          // laid the header out. Reading a ref before the state flip gave
          // a stale rect, which put the panel off-screen.
          const box = trigger.current?.getBoundingClientRect()
          if (box) setAnchor({ top: box.bottom + 8, right: window.innerWidth - box.right })
          setOpen((current) => !current)
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl border text-[12px] font-semibold transition-colors duration-200 ${
          open
            ? 'border-accent/40 bg-accent/15 text-accent-hi'
            : 'border-edge text-ink-dim hover:border-edge-hi hover:text-ink'
        }`}
      >
        <span aria-hidden="true">{initial}</span>
      </button>

      {open &&
        anchor &&
        createPortal(
          <div
            ref={panel}
            role="menu"
            style={{ top: anchor.top, right: anchor.right }}
            className="glass animate-pop fixed z-[60] w-56 origin-top-right rounded-2xl p-1.5"
          >
            <div className="px-3 py-2">
              <p className="truncate text-[13px] font-medium text-ink">{user.name}</p>
              <p className="truncate text-[12px] text-ink-faint">{user.email}</p>
            </div>

            <div className="my-1 h-px bg-edge" />

            <a
              href="https://github.com/gauri2029/design-drift"
              target="_blank"
              rel="noreferrer"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] text-ink-dim transition-colors duration-200 hover:bg-tint hover:text-ink"
            >
              <svg
                viewBox="0 0 16 16"
                aria-hidden="true"
                className="h-3.5 w-3.5 shrink-0"
                fill="currentColor"
              >
                <path d="M8 0a8 8 0 0 0-2.53 15.59c.4.07.55-.17.55-.38v-1.34c-2.23.49-2.7-1.07-2.7-1.07-.36-.93-.89-1.18-.89-1.18-.73-.5.05-.49.05-.49.8.06 1.23.83 1.23.83.72 1.23 1.88.87 2.34.67.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.03 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.14.46.55.38A8 8 0 0 0 8 0Z" />
              </svg>
              Source on GitHub
            </a>

            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false)
                onSignOut()
              }}
              className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-[13px] text-ink-dim transition-colors duration-200 hover:bg-bad/10 hover:text-bad"
            >
              <svg
                viewBox="0 0 24 24"
                aria-hidden="true"
                className="h-3.5 w-3.5 shrink-0"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
              </svg>
              Sign out
            </button>
          </div>,
          document.body,
        )}
    </>
  )
}
