"""Shared LangGraph state for the Design QA workflow (see
docs/architecture.md's "Runtime multi-agent workflow"). One typed Pydantic
model that every node reads/writes explicit fields on — no free-form
message-passing between agents (docs/principles.md #4).

Grows one node's worth of fields at a time as each vertical slice lands
(docs/principles.md #1): Design Analysis, Production Analysis, Visual
Comparison, Accessibility, now the findings aggregation. Later agents add
their own fields the same way rather than this being speculatively modeled
up front.
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.agents.types import (
    AccessibilityInterpretation,
    AggregatedFindings,
    DesignAnalysisResult,
)
from app.integrations.axe.types import AccessibilityReport
from app.integrations.imaging.types import ComparisonResult
from app.integrations.llm.types import VisualReviewResult


class DesignQAState(BaseModel):
    project_id: UUID

    # --- Design Analysis Agent's inputs/output ---
    # Raw node data from Project.figma_data (see
    # app.services.projects._fetch_and_store_figma_data) — name, type,
    # layout_mode, absolute_bounding_box, etc. Plain dict, not FigmaNode:
    # the state doesn't need the full typed model, just what the agent's
    # prompt reads off it.
    figma_node: dict[str, Any]
    figma_screenshot: bytes
    design_analysis: DesignAnalysisResult | None = None

    # --- Production Analysis Agent's inputs/output ---
    # From Project.target_url/target_selector — see
    # app.services.design_analysis.
    target_url: str
    target_selector: str | None = None
    production_screenshot: bytes | None = None

    # --- Visual Comparison Agent's output ---
    # comparison_result/diff_screenshot are its deterministic tool call
    # (image diffing); visual_comparison is its LLM judgment call on top of
    # that — see app.agents.visual_comparison.
    comparison_result: ComparisonResult | None = None
    diff_screenshot: bytes | None = None
    visual_comparison: VisualReviewResult | None = None

    # --- Accessibility Agent's output ---
    # accessibility_report is its deterministic tool call (axe-core);
    # accessibility_interpretation is its LLM judgment on top of that —
    # see app.agents.accessibility.
    accessibility_report: AccessibilityReport | None = None
    accessibility_interpretation: AccessibilityInterpretation | None = None

    # --- Findings aggregation's output ---
    # Every agent's findings merged into one triaged list, plus the
    # problems_found flag docs/architecture.md's flow branches on — see
    # app.agents.aggregate_findings.
    aggregated_findings: AggregatedFindings | None = None

    # Set by the Supervisor when it decides the workflow can't proceed
    # (e.g. no usable Figma data) — distinct from a node's own tool/LLM
    # call failing, which propagates as a normal exception (see
    # app.agents.design_analysis's module docstring).
    error: str | None = None
