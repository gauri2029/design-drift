"""Supervisor node: owns routing for the Design QA workflow (see
docs/architecture.md's runtime-agent table — "owns workflow state, routes
between agents; no tools of its own").

Routing is mostly a "what hasn't run yet" check over state, in the same
order nodes appear in docs/architecture.md's flow: Design Analysis,
Production Analysis, Visual Comparison, Accessibility, the findings
aggregation, then Code Analysis. Adding a later agent (Fix Agent, ...)
means adding one more branch here and to the graph's path_map in
app.graph.workflow — each new agent doesn't need to decide for itself
whether it should run.

Code Analysis is the first node that is *not* unconditional — it's
docs/architecture.md's `route: problems found?` fork, and it's a real
fork now that there's somewhere other than END to go. Two things have to
hold for it to run: the aggregation found problems (nothing to locate
otherwise), and the project has a usable source checkout. A project
without one still gets the four inspection agents and simply ends after
aggregation, rather than the run failing — configuring a checkout is
optional (see Project.source_path).
"""

from typing import Any

from app.graph.state import DesignQAState

NODE_DESIGN_ANALYSIS = "design_analysis"
NODE_PRODUCTION_ANALYSIS = "production_analysis"
NODE_VISUAL_COMPARISON = "visual_comparison"
NODE_ACCESSIBILITY = "accessibility"
NODE_AGGREGATE_FINDINGS = "aggregate_findings"
NODE_CODE_ANALYSIS = "code_analysis"
NODE_FIX = "fix"
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
    if _should_run_code_analysis(state):
        return NODE_CODE_ANALYSIS
    if _should_run_fix(state):
        return NODE_FIX
    return NODE_END


def _should_run_code_analysis(state: DesignQAState) -> bool:
    if state.code_analysis is not None:
        return False  # already ran
    if state.source_root is None:
        return False  # project has no source checkout to search
    # `problems_found` is the fork docs/architecture.md calls
    # `route: problems found?` — with nothing found, there's nothing to
    # locate in the code, so the run ends here.
    return bool(state.aggregated_findings and state.aggregated_findings.problems_found)


def _should_run_fix(state: DesignQAState) -> bool:
    if state.fix_proposal is not None:
        return False  # already ran
    if state.code_analysis is None or state.source_root is None:
        return False  # nothing was located, so there's nothing to patch
    # A patch needs a file and a line range. A run where every finding came
    # back no_match has neither, and asking for a fix anyway would be
    # asking the model to invent one (see app.agents.fix's docstring).
    return any(not location.no_match for location in state.code_analysis.locations)
