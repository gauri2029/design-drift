import { useCallback, useEffect, useState } from 'react'
import { createReview as createReviewRequest, fetchReviews, type Review } from '../lib/api'

type Status = 'loading' | 'ready' | 'error'

interface UseReviewsResult {
  latestReview: Review | null
  status: Status
  error: string | null
  running: boolean
  runReview: () => Promise<void>
}

export function useReviews(projectId: string, scanId: string): UseReviewsResult {
  // Assumes the caller remounts this hook per scan (`key={scanId}`), same
  // rationale as useScans — see its comment.
  const [reviews, setReviews] = useState<Review[]>([])
  const [status, setStatus] = useState<Status>('loading')
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    let cancelled = false

    fetchReviews(projectId, scanId)
      .then((data) => {
        if (cancelled) return
        setReviews(data)
        setStatus('ready')
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load reviews')
        setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [projectId, scanId])

  const runReview = useCallback(async () => {
    setRunning(true)
    try {
      const review = await createReviewRequest(projectId, scanId)
      setReviews((current) => [review, ...current])
      setError(null)
    } finally {
      setRunning(false)
    }
  }, [projectId, scanId])

  return {
    latestReview: reviews[0] ?? null,
    status,
    error,
    running,
    runReview,
  }
}
