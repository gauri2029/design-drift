import { useCallback, useEffect, useState } from 'react'
import {
  applyDesignAnalysisFixes,
  createDesignAnalysis as createDesignAnalysisRequest,
  fetchDesignAnalyses,
  reviewDesignAnalysisFixes,
  verifyDesignAnalysis,
  type DesignAnalysis,
  type FixDecisionItem,
} from '../lib/api'

type Status = 'loading' | 'ready' | 'error'

interface UseDesignAnalysesResult {
  latestAnalysis: DesignAnalysis | null
  status: Status
  error: string | null
  running: boolean
  runAnalysis: () => Promise<void>
  reviewFixes: (analysisId: string, decisions: FixDecisionItem[]) => Promise<void>
  applyFixes: (analysisId: string) => Promise<void>
  verifyFixes: (analysisId: string, targetUrl?: string) => Promise<void>
}

export function useDesignAnalyses(projectId: string): UseDesignAnalysesResult {
  // Assumes the caller remounts this hook per project (`key={project.id}`),
  // same rationale as useScans — see its comment.
  const [analyses, setAnalyses] = useState<DesignAnalysis[]>([])
  const [status, setStatus] = useState<Status>('loading')
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    let cancelled = false

    fetchDesignAnalyses(projectId)
      .then((data) => {
        if (cancelled) return
        setAnalyses(data)
        setStatus('ready')
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load design analyses')
        setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [projectId])

  const runAnalysis = useCallback(async () => {
    setRunning(true)
    try {
      const analysis = await createDesignAnalysisRequest(projectId)
      setAnalyses((current) => [analysis, ...current])
      setError(null)
    } finally {
      setRunning(false)
    }
  }, [projectId])

  const replaceAnalysis = useCallback((updated: DesignAnalysis) => {
    setAnalyses((current) =>
      current.map((analysis) => (analysis.id === updated.id ? updated : analysis)),
    )
  }, [])

  const reviewFixes = useCallback(
    async (analysisId: string, decisions: FixDecisionItem[]) => {
      replaceAnalysis(await reviewDesignAnalysisFixes(projectId, analysisId, decisions))
    },
    [projectId, replaceAnalysis],
  )

  const applyFixes = useCallback(
    async (analysisId: string) => {
      replaceAnalysis(await applyDesignAnalysisFixes(projectId, analysisId))
    },
    [projectId, replaceAnalysis],
  )

  const verifyFixes = useCallback(
    async (analysisId: string, targetUrl?: string) => {
      replaceAnalysis(await verifyDesignAnalysis(projectId, analysisId, targetUrl))
    },
    [projectId, replaceAnalysis],
  )

  return {
    // The list endpoint returns newest first, so [0] is the latest run.
    latestAnalysis: analyses[0] ?? null,
    status,
    error,
    running,
    runAnalysis,
    reviewFixes,
    applyFixes,
    verifyFixes,
  }
}
