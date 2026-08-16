import { useCallback, useEffect, useState } from 'react'
import {
  createScan as createScanRequest,
  createScansAtAllBreakpoints,
  fetchScans,
  type Breakpoint,
  type Scan,
} from '../lib/api'

type Status = 'idle' | 'loading' | 'ready' | 'error'

interface UseScansResult {
  scans: Scan[]
  status: Status
  error: string | null
  selectedScan: Scan | null
  selectScan: (id: string) => void
  running: boolean
  runScan: (breakpoint?: Breakpoint) => Promise<void>
  runAllBreakpoints: () => Promise<void>
}

export function useScans(projectId: string): UseScansResult {
  // Assumes the caller remounts this hook per project (e.g. `key={project.id}`
  // on the consuming component) rather than this hook resetting `status`
  // itself when `projectId` changes — avoids a synchronous setState at the
  // top of the effect below, which would trigger a redundant extra render.
  const [scans, setScans] = useState<Scan[]>([])
  const [status, setStatus] = useState<Status>('loading')
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    let cancelled = false

    fetchScans(projectId)
      .then((data) => {
        if (cancelled) return
        setScans(data)
        setStatus('ready')
        setSelectedId(data[0]?.id ?? null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load scans')
        setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [projectId])

  const runScan = useCallback(
    async (breakpoint?: Breakpoint) => {
      setRunning(true)
      try {
        const scan = await createScanRequest(projectId, breakpoint)
        setScans((current) => [scan, ...current])
        setSelectedId(scan.id)
        setError(null)
      } finally {
        setRunning(false)
      }
    },
    [projectId],
  )

  const runAllBreakpoints = useCallback(async () => {
    setRunning(true)
    try {
      const newScans = await createScansAtAllBreakpoints(projectId)
      setScans((current) => [...newScans, ...current])
      setSelectedId(newScans[0]?.id ?? null)
      setError(null)
    } finally {
      setRunning(false)
    }
  }, [projectId])

  return {
    scans,
    status,
    error,
    selectedScan: scans.find((scan) => scan.id === selectedId) ?? null,
    selectScan: setSelectedId,
    running,
    runScan,
    runAllBreakpoints,
  }
}
