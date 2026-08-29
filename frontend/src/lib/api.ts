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
  source_path: string | null
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
  source_path?: string
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

// Mirrors app/integrations/playwright/breakpoints.py:STANDARD_BREAKPOINTS.
// Kept separate from MATCH_FIGMA_BREAKPOINT: "run all breakpoints" only
// iterates this set, same as create_scans_at_all_breakpoints on the backend.
export const STANDARD_BREAKPOINTS = ['mobile', 'tablet', 'desktop'] as const
export type Breakpoint = (typeof STANDARD_BREAKPOINTS)[number]

// Mirrors app/integrations/playwright/breakpoints.py:MATCH_FIGMA_BREAKPOINT.
// The recommended/default fidelity scan mode: viewport width tracks the
// Figma frame's own width instead of a fixed preset.
export const MATCH_FIGMA_BREAKPOINT = 'match_figma' as const
export type ScanMode = Breakpoint | typeof MATCH_FIGMA_BREAKPOINT

// Mirrors app/integrations/axe/types.py. Deterministic axe-core output —
// no AI interpretation applied yet.
export interface AxeNode {
  target: string[]
  html: string | null
  failureSummary: string | null
}

export interface AxeViolation {
  id: string
  impact: string | null
  description: string
  help: string
  helpUrl: string
  tags: string[]
  nodes: AxeNode[]
}

export interface AccessibilityReport {
  violations: AxeViolation[]
  violation_count: number
}

// Mirrors app/schemas/scan.py:ScanRead.
export interface Scan {
  id: string
  project_id: string
  viewport_width: number
  viewport_height: number
  breakpoint: ScanMode | null
  production_screenshot_key: string
  diff_image_key: string
  comparison_result: ComparisonResult
  accessibility_report: AccessibilityReport
  created_at: string
}

export async function fetchScans(projectId: string): Promise<Scan[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/scans`)

  if (!response.ok) {
    throw new Error(`Failed to list scans (${response.status})`)
  }

  return (await response.json()) as Scan[]
}

export async function createScan(projectId: string, breakpoint?: ScanMode): Promise<Scan> {
  const response = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/scans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(breakpoint ? { breakpoint } : {}),
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `Failed to run scan (${response.status})`)
  }

  return (await response.json()) as Scan
}

export async function createScansAtAllBreakpoints(projectId: string): Promise<Scan[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/scans/breakpoints`, {
    method: 'POST',
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `Failed to run breakpoint scans (${response.status})`)
  }

  return (await response.json()) as Scan[]
}

export function scanProductionUrl(projectId: string, scanId: string): string {
  return `${API_BASE_URL}/api/v1/projects/${projectId}/scans/${scanId}/production`
}

// Mirrors app/integrations/llm/types.py. Produced by one multimodal Claude
// call — a judgment layer on top of the deterministic comparison_result
// and accessibility_report above, not a replacement for either.
export type FindingCategory =
  | 'layout'
  | 'spacing'
  | 'typography'
  | 'color'
  | 'responsive'
  | 'accessibility'
  | 'component_structure'
  | 'other'

export type FindingSeverity = 'critical' | 'major' | 'minor' | 'cosmetic'

export interface DesignFinding {
  category: FindingCategory
  severity: FindingSeverity
  title: string
  description: string
  evidence: string
  likely_area: string | null
}

export interface VisualReviewResult {
  material_drift_detected: boolean
  summary: string
  findings: DesignFinding[]
}

// Mirrors app/schemas/review.py:ReviewRead.
export interface Review {
  id: string
  scan_id: string
  model: string
  result: VisualReviewResult
  created_at: string
}

export async function fetchReviews(projectId: string, scanId: string): Promise<Review[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/scans/${scanId}/reviews`,
  )

  if (!response.ok) {
    throw new Error(`Failed to list reviews (${response.status})`)
  }

  return (await response.json()) as Review[]
}

export async function createReview(projectId: string, scanId: string): Promise<Review> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/scans/${scanId}/reviews`,
    { method: 'POST' },
  )

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `Failed to run AI review (${response.status})`)
  }

  return (await response.json()) as Review
}

export function scanDiffUrl(projectId: string, scanId: string): string {
  return `${API_BASE_URL}/api/v1/projects/${projectId}/scans/${scanId}/diff`
}

// --- Design QA workflow (LangGraph) --------------------------------------
//
// Mirrors app/schemas/design_analysis.py:DesignAnalysisRead — one run of the
// multi-agent graph (app/graph/workflow.py). Project-scoped, not
// scan-scoped: the graph does its own production capture rather than
// reusing a Scan, so this lives alongside Scan rather than inside it.

// Mirrors app/agents/types.py:DesignAnalysisResult — the Figma side alone.
export interface DesignComponent {
  name: string
  role: string
  notable_styling: string
}

export interface DesignAnalysisResult {
  layout_summary: string
  design_intent: string
  key_components: DesignComponent[]
  implementation_risks: string[]
}

export type AccessibilityPriority = 'high' | 'medium' | 'low'

export interface AccessibilityIssue {
  violation_id: string
  user_impact: string
  priority: AccessibilityPriority
}

export interface AccessibilityInterpretation {
  summary: string
  most_important_issues: AccessibilityIssue[]
}

// Every agent's findings merged onto one scale — see
// app/agents/aggregate_findings.py. `original_severity` keeps the producing
// agent's own word, since normalizing onto `priority` is lossy.
export type FindingSource = 'visual_comparison' | 'accessibility'
export type FindingPriority = 'high' | 'medium' | 'low'

export interface AggregatedFinding {
  source: FindingSource
  priority: FindingPriority
  original_severity: string
  title: string
  detail: string
  likely_area: string | null
}

export interface AggregatedFindings {
  problems_found: boolean
  findings: AggregatedFinding[]
}

export type LocationConfidence = 'high' | 'medium' | 'low'

export interface SourceLocation {
  file_path: string
  line_start: number
  line_end: number
  code_evidence: string
}

export interface FindingLocation {
  finding_title: string
  no_match: boolean
  location: SourceLocation | null
  explanation: string
  confidence: LocationConfidence
}

export interface CodeAnalysisResult {
  summary: string
  locations: FindingLocation[]
}

export interface DesignAnalysis {
  id: string
  project_id: string
  model: string
  result: DesignAnalysisResult
  production_screenshot_key: string | null
  comparison_result: ComparisonResult | null
  diff_image_key: string | null
  visual_comparison: VisualReviewResult | null
  accessibility_report: AccessibilityReport | null
  accessibility_interpretation: AccessibilityInterpretation | null
  aggregated_findings: AggregatedFindings | null
  // Null when the workflow's `problems found?` fork skipped Code Analysis —
  // no problems, or the project has no source checkout configured.
  code_analysis: CodeAnalysisResult | null
  created_at: string
}

export async function fetchDesignAnalyses(projectId: string): Promise<DesignAnalysis[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/design-analysis`)

  if (!response.ok) {
    throw new Error(`Failed to list design analyses (${response.status})`)
  }

  return (await response.json()) as DesignAnalysis[]
}

export async function createDesignAnalysis(projectId: string): Promise<DesignAnalysis> {
  const response = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/design-analysis`, {
    method: 'POST',
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `Failed to run the Design QA workflow (${response.status})`)
  }

  return (await response.json()) as DesignAnalysis
}

export function designAnalysisProductionUrl(projectId: string, analysisId: string): string {
  return `${API_BASE_URL}/api/v1/projects/${projectId}/design-analysis/${analysisId}/production`
}

export function designAnalysisDiffUrl(projectId: string, analysisId: string): string {
  return `${API_BASE_URL}/api/v1/projects/${projectId}/design-analysis/${analysisId}/diff`
}
