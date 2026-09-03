import { useCallback, useEffect, useState } from 'react'
import {
  createDesignAnalysis as createDesignAnalysisRequest,
  fetchDesignAnalyses,
  reviewDesignAnalysisFixes,
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

  const reviewFixes = useCallback(
    async (analysisId: string, decisions: FixDecisionItem[]) => {
      const updated = await reviewDesignAnalysisFixes(projectId, analysisId, decisions)
      setAnalyses((current) =>
        current.map((analysis) => (analysis.id === analysisId ? updated : analysis)),
      )
    },
    [projectId],
  )

  return {
    // The list endpoint returns newest first, so [0] is the latest run.
    latestAnalysis: analyses[0] ?? null,
    status,
    error,
    running,
    runAnalysis,
    reviewFixes,
  }
}
