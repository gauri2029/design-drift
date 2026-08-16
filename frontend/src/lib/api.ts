const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export interface HealthResponse {
  status: string
  service: string
}

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/health`)

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`)
  }

  return (await response.json()) as HealthResponse
}

export interface FigmaBoundingBox {
  x: number
  y: number
  width: number
  height: number
}

// Mirrors app/integrations/figma/types.py:FigmaNode. Only the fields the
// preview panel renders are declared here — the backend's model carries
// more (fills, strokes, text style, ...) for later phases.
export interface FigmaNode {
  id: string
  name: string
  type: string
  visible: boolean
  absoluteBoundingBox: FigmaBoundingBox | null
  layoutMode: string | null
  children: FigmaNode[]
}

// Mirrors app/schemas/project.py:ProjectRead. Note the casing split: the
// outer schema is plain (snake_case) Pydantic, but `figma_data` nests a
// FigmaNode, which serializes camelCase via its alias generator.
export interface Project {
  id: string
  name: string
  figma_file_key: string
  figma_node_id: string
  target_url: string
  figma_data: FigmaNode | null
  figma_screenshot_key: string | null
  figma_fetched_at: string | null
  created_at: string
  updated_at: string
}

export interface ProjectCreateInput {
  name: string
  figma_file_key: string
  figma_node_id: string
  target_url: string
}

export async function fetchProjects(): Promise<Project[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/projects`)

  if (!response.ok) {
    throw new Error(`Failed to list projects (${response.status})`)
  }

  return (await response.json()) as Project[]
}

export async function createProject(input: ProjectCreateInput): Promise<Project> {
  const response = await fetch(`${API_BASE_URL}/api/v1/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `Failed to create project (${response.status})`)
  }

  return (await response.json()) as Project
}

export function projectScreenshotUrl(projectId: string): string {
  return `${API_BASE_URL}/api/v1/projects/${projectId}/figma/screenshot`
}
