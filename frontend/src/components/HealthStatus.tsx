import { useEffect, useState } from 'react'
import { fetchHealth } from '../lib/api'

type Status = 'loading' | 'connected' | 'error'

export function HealthStatus() {
  const [status, setStatus] = useState<Status>('loading')
  const [service, setService] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    fetchHealth()
      .then((health) => {
        if (cancelled) return
        setService(health.service)
        setStatus('connected')
      })
      .catch(() => {
        if (cancelled) return
        setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [])

  const statusConfig: Record<Status, { label: string; dot: string; text: string }> = {
    loading: { label: 'Checking backend…', dot: 'bg-slate-400', text: 'text-slate-500 dark:text-slate-400' },
    connected: {
      label: service ? `Connected to ${service}` : 'Connected',
      dot: 'bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.15)]',
      text: 'text-emerald-700 dark:text-emerald-400',
    },
    error: { label: 'Backend unreachable', dot: 'bg-red-500 shadow-[0_0_0_3px_rgba(239,68,68,0.15)]', text: 'text-red-700 dark:text-red-400' },
  }

  const { label, dot, text } = statusConfig[status]

  return (
    <div
      role="status"
      aria-live="polite"
      className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden="true" />
      <span className={text}>{label}</span>
    </div>
  )
}
