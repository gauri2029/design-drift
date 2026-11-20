import { useEffect, useState } from 'react'
import { fetchDemoStatus, type DemoStatus } from '../lib/api'

export interface DemoState {
  /** True when this deployment serves the read-only showcase *and* the
   * visitor is browsing it anonymously.
   *
   * Both conditions, deliberately. A signed-in user on the same deployment
   * is working with their own projects and should see no demo framing at
   * all: the lock only ever applies to the showcase account's data, so
   * telling a real user their run is "precomputed" would be false.
   */
  browsingDemo: boolean
  /** Whose projects an anonymous visitor is looking at. */
  ownerName: string | null
}

/** Whether to present this session as the public demo.
 *
 * `signedIn` is passed in rather than read from useAuth here, so this hook
 * stays a thin wrapper over one request and App keeps a single source of
 * truth for identity.
 */
export function useDemo(signedIn: boolean): DemoState {
  // Only what the request returns is state. Whether to *use* it is derived
  // below, which is what keeps `signedIn` out of the effect: resetting
  // state from inside an effect when it changed would be a second render
  // pass to compute something already known during the first.
  const [status, setStatus] = useState<DemoStatus | null>(null)

  useEffect(() => {
    // Asked once per mount, and skipped entirely while signed in - a real
    // user's own projects are never the showcase, so there is nothing to
    // learn. Already-fetched status is kept rather than cleared: signing
    // out should not need a second round trip to restore the demo view.
    if (signedIn || status !== null) return

    let cancelled = false
    void fetchDemoStatus().then((fetched) => {
      if (!cancelled) setStatus(fetched)
    })

    return () => {
      cancelled = true
    }
  }, [signedIn, status])

  // `seeded` as well as `enabled`: a deployment switched on before its seed
  // has run should look like a normal empty app rather than promise a demo
  // that is not there.
  const browsingDemo = !signedIn && status !== null && status.enabled && status.seeded

  return {
    browsingDemo,
    ownerName: browsingDemo ? status.user_name : null,
  }
}
