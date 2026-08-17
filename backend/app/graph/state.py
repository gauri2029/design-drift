"""Shared LangGraph state for the Design QA workflow (see
docs/architecture.md's "Runtime multi-agent workflow"). One typed Pydantic
model that every node reads/writes explicit fields on — no free-form
message-passing between agents (docs/principles.md #4).

Only the Design Analysis vertical slice exists so far: this state carries
just what that agent needs (a Figma node + its rendered screenshot) plus a
result/error slot. Later phases add fields as each new agent lands
(production capture, comparison findings, accessibility, ...) rather than
speculatively modeling the full workflow now (docs/principles.md #1).
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.agents.types import DesignAnalysisResult


class DesignAnalysisState(BaseModel):
    project_id: UUID
    # Raw node data from Project.figma_data (see
    # app.services.projects._fetch_and_store_figma_data) — name, type,
    # layout_mode, absolute_bounding_box, etc. Plain dict, not FigmaNode:
    # the state doesn't need the full typed model, just what the agent's
    # prompt reads off it.
    figma_node: dict[str, Any]
    figma_screenshot: bytes

    # Set by the Design Analysis Agent once it succeeds.
    result: DesignAnalysisResult | None = None
    # Set by the Supervisor when it decides the workflow can't proceed
    # (e.g. no usable Figma data) — distinct from an LLM call failing,
    # which propagates as a normal exception (see
    # app.agents.design_analysis's module docstring).
    error: str | None = None
