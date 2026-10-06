import { useCallback, useEffect, useRef, useState } from 'react'

/** Interaction primitives, in one file so the performance rules have a
 * single place to be audited.
 *
 * Three rules hold throughout:
 *   1. No pointer handler sets React state. Every per-frame effect writes a
 *      CSS custom property on a DOM node, which the compositor reads — a
 *      render on pointermove would be a dropped frame per move.
 *   2. Only `transform` and `opacity` animate, never geometry.
 *   3. Work is coalesced into one requestAnimationFrame, so a pointer
 *      firing at 1000Hz still costs one write per displayed frame.
 */

function reducedMotion(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Light that follows the cursor across an element.
 *
 * Writes `--mx`/`--my` only; the gradient lives in CSS (`.lit`). Spread the
 * returned handler onto any element that also carries the `lit` class.
 */
export function useCursorLight<T extends HTMLElement>() {
  const frame = useRef(0)
  const pending = useRef<{ el: T; x: number; y: number } | null>(null)

  useEffect(() => () => cancelAnimationFrame(frame.current), [])

  const onPointerMove = useCallback((event: React.PointerEvent<T>) => {
    if (reducedMotion()) return
    const el = event.currentTarget
    const box = el.getBoundingClientRect()
    pending.current = {
      el,
      x: ((event.clientX - box.left) / box.width) * 100,
      y: ((event.clientY - box.top) / box.height) * 100,
    }
    // Coalesced: a pointer reporting faster than the display still costs
    // one write per painted frame.
    if (frame.current) return
    frame.current = requestAnimationFrame(() => {
      frame.current = 0
      const next = pending.current
      if (!next) return
      next.el.style.setProperty('--mx', `${next.x}%`)
      next.el.style.setProperty('--my', `${next.y}%`)
    })
  }, [])

  return { onPointerMove }
}

/** A control that leans toward the cursor.
 *
 * Writes `--pull-x`/`--pull-y` rather than `transform`, so the lean composes
 * with the `.tilt` hover and press transforms instead of overwriting them —
 * setting `transform` here is what made the button jump in an earlier pass.
 */
export function useMagnetic<T extends HTMLElement>(max = 3) {
  const frame = useRef(0)
  const pending = useRef<{ el: T; x: number; y: number } | null>(null)

  useEffect(() => () => cancelAnimationFrame(frame.current), [])

  const onPointerMove = useCallback(
    (event: React.PointerEvent<T>) => {
      if (reducedMotion() || max === 0) return
      const el = event.currentTarget
      const box = el.getBoundingClientRect()
      pending.current = {
        el,
        x: ((event.clientX - box.left) / box.width - 0.5) * 2 * max,
        y: ((event.clientY - box.top) / box.height - 0.5) * 2 * max,
      }
      if (frame.current) return
      frame.current = requestAnimationFrame(() => {
        frame.current = 0
        const next = pending.current
        if (!next) return
        next.el.style.setProperty('--pull-x', `${next.x}px`)
        next.el.style.setProperty('--pull-y', `${next.y}px`)
      })
    },
    [max],
  )

  const onPointerLeave = useCallback((event: React.PointerEvent<T>) => {
    event.currentTarget.style.removeProperty('--pull-x')
    event.currentTarget.style.removeProperty('--pull-y')
  }, [])

  return { onPointerMove, onPointerLeave }
}

/** Count a number up when it changes.
 *
 * The one animation here that sets state, because digits are text and text
 * cannot be composited. Bounded: ~14 renders over 550ms for one small
 * element, and it short-circuits under reduced motion. */
export function useCountUp(target: number, duration = 550): number {
  const [value, setValue] = useState(target)
  const from = useRef(target)
  const frame = useRef(0)

  useEffect(() => {
    if (reducedMotion() || target === from.current) {
      from.current = target
      setValue(target)
      return
    }

    const start = performance.now()
    const origin = from.current
    from.current = target

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      // Ease-out: fast at first, settling at the end, so the final number
      // appears to land rather than to stop.
      const eased = 1 - Math.pow(1 - t, 3)
      setValue(Math.round(origin + (target - origin) * eased))
      if (t < 1) frame.current = requestAnimationFrame(tick)
    }

    frame.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame.current)
  }, [target, duration])

  return value
}

export type Theme = 'dark' | 'light'

/** The theme toggle.
 *
 * Reads what index.html already applied before first paint, so this never
 * causes the flash it exists to prevent. When nothing was stored it resolves
 * the OS preference and writes it to the element — leaving `data-theme`
 * unset would let the label and the painted theme disagree, and the first
 * click would then appear to do nothing. */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof document === 'undefined') return 'dark'
    const set = document.documentElement.dataset.theme
    if (set === 'light' || set === 'dark') return set
    return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: light)').matches
      ? 'light'
      : 'dark'
  })

  // One source of truth. The attribute lives outside React's tree, so this
  // is exactly the synchronisation an effect is for.
  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === 'dark' ? 'light' : 'dark'
      try {
        localStorage.setItem('drift-theme', next)
      } catch {
        // Private browsing: the theme still applies for this session.
      }
      return next
    })
  }, [])

  return [theme, toggle]
}

/** Run a state change inside a View Transition where the browser has one.
 *
 * Everything still works without it — the update simply happens without a
 * crossfade, which is what every browser did before the API existed. */
export function withViewTransition(update: () => void) {
  const doc = document as Document & {
    startViewTransition?: (callback: () => void) => unknown
  }
  if (typeof doc.startViewTransition !== 'function' || reducedMotion()) {
    update()
    return
  }
  doc.startViewTransition(update)
}
