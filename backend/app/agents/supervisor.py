"""Supervisor node: owns routing for the Design QA workflow (see
docs/architecture.md's runtime-agent table — "owns workflow state, routes
between agents; no tools of its own").

Routing is a simple "what hasn't run yet" check over state, in the same
order agents appear in docs/architecture.md's flow: Design Analysis, then
Production Analysis. Adding a later agent (Visual Comparison, ...) means
adding one more `if state.<its output> is None: return NODE_<it>` line
here and to the graph's path_map in app.graph.workflow — each new agent
doesn't need to decide for itself whether it should run.
"""

from typing import Any

from app.graph.state import DesignQAState

NODE_DESIGN_ANALYSIS = "design_analysis"
NODE_PRODUCTION_ANALYSIS = "production_analysis"
NODE_END = "end"


def supervisor_node(state: DesignQAState) -> dict[str, Any]:
    if not state.figma_node:
        return {"error": "project's Figma node has no recorded data; nothing to analyze"}
    return {}


def route_after_supervisor(state: DesignQAState) -> str:
    if state.error is not None:
        return NODE_END
    if state.design_analysis is None:
        return NODE_DESIGN_ANALYSIS
    if state.production_screenshot is None:
        return NODE_PRODUCTION_ANALYSIS
    return NODE_END
