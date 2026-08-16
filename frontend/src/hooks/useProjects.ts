import { useCallback, useEffect, useState } from 'react'
import {
  createProject as createProjectRequest,
  fetchProjects,
  type Project,
  type ProjectCreateInput,
} from '../lib/api'

type Status = 'loading' | 'ready' | 'error'

interface UseProjectsResult {
  projects: Project[]
  status: Status
  error: string | null
  selectedProject: Project | null
  selectProject: (id: string) => void
  submitting: boolean
  createProject: (input: ProjectCreateInput) => Promise<void>
}

export function useProjects(): UseProjectsResult {
  const [projects, setProjects] = useState<Project[]>([])
  const [status, setStatus] = useState<Status>('loading')
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let cancelled = false

    fetchProjects()
      .then((data) => {
        if (cancelled) return
        setProjects(data)
        setStatus('ready')
        setSelectedId((current) => current ?? (data[0]?.id ?? null))
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load projects')
        setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [])

  const createProject = useCallback(async (input: ProjectCreateInput) => {
    setSubmitting(true)
    try {
      const project = await createProjectRequest(input)
      setProjects((current) => [project, ...current])
      setSelectedId(project.id)
      setError(null)
    } finally {
      setSubmitting(false)
    }
  }, [])

  return {
    projects,
    status,
    error,
    selectedProject: projects.find((project) => project.id === selectedId) ?? null,
    selectProject: setSelectedId,
    submitting,
    createProject,
  }
}
