"""Supervisor node: owns routing for the Design QA workflow (see
docs/architecture.md's runtime-agent table — "owns workflow state, routes
between agents; no tools of its own").

Only one real downstream agent exists yet (Design Analysis), so this
mostly validates that there's usable Figma data before spending an LLM
call on it. The point of giving it its own node — rather than inlining a
routing function somewhere — is that later phases (Production Analysis,
Visual Comparison, ...) extend *this* function's routing decision and the
graph's path_map in app.graph.workflow, instead of each new agent deciding
for itself whether it should run.
"""

from typing import Any

from app.graph.state import DesignAnalysisState

NODE_DESIGN_ANALYSIS = "design_analysis"
NODE_END = "end"


def supervisor_node(state: DesignAnalysisState) -> dict[str, Any]:
    if not state.figma_node:
        return {"error": "project's Figma node has no recorded data; nothing to analyze"}
    return {}


def route_after_supervisor(state: DesignAnalysisState) -> str:
    if state.error is not None or state.result is not None:
        return NODE_END
    return NODE_DESIGN_ANALYSIS
