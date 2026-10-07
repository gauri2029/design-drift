import { useEffect, useState } from 'react'
import { authHeader } from './auth'

/** Fetches an image that requires authentication and returns a URL an
 * `<img>` can use.
 *
 * A browser won't attach an Authorization header to `<img src>`, and the
 * screenshot endpoints are owner-gated like every other route. So the bytes
 * are fetched with the token, wrapped in a blob URL, and that is what the
 * tag renders.
 *
 * Returns `null` while loading and on failure alike: every caller already
 * renders a placeholder for a capture that doesn't exist yet (a project
 * whose Figma fetch hasn't run legitimately 404s), and that same placeholder
 * is the right thing to show for a moment while bytes arrive.
 */
export function useAuthedImage(src: string | undefined): string | null {
  // Keyed on the src the blob came from, so a changed src can't briefly
  // show the previous image, and so clearing it needs no setState in an
  // effect body (which cascades renders — react-hooks/set-state-in-effect).
  const [loaded, setLoaded] = useState<{ src: string; url: string } | null>(null)

  useEffect(() => {
    if (!src) return

    let revoked = false
    let created: string | null = null

    void (async () => {
      try {
        const response = await fetch(src, { headers: authHeader() })
        if (!response.ok) return
        const blob = await response.blob()
        // The effect can be torn down mid-await — creating the URL then
        // would leak it, since the cleanup below has already run.
        if (revoked) return
        created = URL.createObjectURL(blob)
        setLoaded({ src, url: created })
      } catch {
        // Offline or aborted: the placeholder stands.
      }
    })()

    return () => {
      revoked = true
      // Each blob holds its bytes in memory until explicitly released, and
      // these are full-page screenshots.
      if (created) URL.revokeObjectURL(created)
    }
  }, [src])

  // Derived rather than stored: a src that changed mid-flight reads as "not
  // loaded yet" without an extra render to clear the old value.
  return loaded && loaded.src === src ? loaded.url : null
}
