"""Supervisor node: owns routing for the Design QA workflow (see
docs/architecture.md's runtime-agent table — "owns workflow state, routes
between agents; no tools of its own").

Routing is a simple "what hasn't run yet" check over state, in the same
order nodes appear in docs/architecture.md's flow: Design Analysis,
Production Analysis, Visual Comparison, Accessibility, then the findings
aggregation. Adding a later agent (Code Analysis, ...) means adding one
more `if state.<its output> is None: return NODE_<it>` line here and to
the graph's path_map in app.graph.workflow — each new agent doesn't need
to decide for itself whether it should run.

Note what this deliberately does *not* do yet: docs/architecture.md's
flow forks on `route: problems found?` after aggregation, but both
branches would currently land on END, since the Code Analysis Agent the
"yes" branch leads to doesn't exist. The data that fork will read
(`aggregated_findings.problems_found`) is computed and persisted now; the
fork itself lands when there's somewhere different to fork to.
"""

from typing import Any

from app.graph.state import DesignQAState

NODE_DESIGN_ANALYSIS = "design_analysis"
NODE_PRODUCTION_ANALYSIS = "production_analysis"
NODE_VISUAL_COMPARISON = "visual_comparison"
NODE_ACCESSIBILITY = "accessibility"
NODE_AGGREGATE_FINDINGS = "aggregate_findings"
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
    if state.visual_comparison is None:
        return NODE_VISUAL_COMPARISON
    if state.accessibility_report is None:
        return NODE_ACCESSIBILITY
    if state.aggregated_findings is None:
        return NODE_AGGREGATE_FINDINGS
    return NODE_END
