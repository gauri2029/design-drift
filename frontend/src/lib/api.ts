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
  target_selector: string | null
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
  target_selector?: string
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

export interface ImageDimensions {
  width: number
  height: number
}

// Mirrors app/integrations/imaging/types.py:ComparisonResult. A raw pixel
// mismatch percentage from deterministic image diffing — NOT an AI-judged
// design fidelity score. Categorized findings/severity require visual
// reasoning, which is a later phase.
export interface ComparisonResult {
  expected_dimensions: ImageDimensions
  actual_dimensions: ImageDimensions
  dimensions_match: boolean
  compared_dimensions: ImageDimensions
  mismatched_pixels: number
  total_pixels: number
  mismatch_percentage: number
}

// Mirrors app/schemas/scan.py:ScanRead.
export interface Scan {
  id: string
  project_id: string
  viewport_width: number
  viewport_height: number
  production_screenshot_key: string
  diff_image_key: string
  comparison_result: ComparisonResult
  created_at: string
}

export async function fetchScans(projectId: string): Promise<Scan[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/scans`)

  if (!response.ok) {
    throw new Error(`Failed to list scans (${response.status})`)
  }

  return (await response.json()) as Scan[]
}

export async function createScan(projectId: string): Promise<Scan> {
  const response = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/scans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `Failed to run scan (${response.status})`)
  }

  return (await response.json()) as Scan
}

export function scanProductionUrl(projectId: string, scanId: string): string {
  return `${API_BASE_URL}/api/v1/projects/${projectId}/scans/${scanId}/production`
}

export function scanDiffUrl(projectId: string, scanId: string): string {
  return `${API_BASE_URL}/api/v1/projects/${projectId}/scans/${scanId}/diff`
}
