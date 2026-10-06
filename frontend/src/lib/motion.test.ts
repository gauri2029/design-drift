import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { useTheme } from './motion'

/** A reload: nothing of the previous page survives but localStorage.
 *
 * The data-theme attribute is what useTheme writes to the live document,
 * so leaving it set would let the next mount read its own last answer
 * instead of the stored preference — which is exactly the bug this file
 * is here to catch.
 */
function reload() {
  delete document.documentElement.dataset.theme
}

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear()
    reload()
  })

  afterEach(() => {
    localStorage.clear()
    reload()
  })

  it('persists a chosen theme and reads it back on the next visit', () => {
    const first = renderHook(() => useTheme())
    const initial = first.result.current[0]

    act(() => first.result.current[1]())
    const chosen = first.result.current[0]
    expect(chosen).not.toBe(initial)
    first.unmount()

    reload()
    const second = renderHook(() => useTheme())

    // The toggle wrote 'drift-theme' but the initializer never read it, so
    // the choice was silently discarded on every reload.
    expect(second.result.current[0]).toBe(chosen)
    expect(document.documentElement.dataset.theme).toBe(chosen)
  })

  it('ignores a junk value rather than rendering an unknown theme', () => {
    localStorage.setItem('drift-theme', 'neon')
    const { result } = renderHook(() => useTheme())

    expect(['light', 'dark']).toContain(result.current[0])
  })

  it('an already-set attribute wins, so the page never repaints on mount', () => {
    localStorage.setItem('drift-theme', 'dark')
    document.documentElement.dataset.theme = 'light'

    expect(renderHook(() => useTheme()).result.current[0]).toBe('light')
  })
})
