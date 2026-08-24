"""Builds and compiles the Design QA LangGraph workflow (see
docs/architecture.md's "Runtime multi-agent workflow"). Six vertical
slices exist so far:

    START -> supervisor -> (design_analysis -> supervisor)*
                         -> (production_analysis -> supervisor)*
                         -> (visual_comparison -> supervisor)*
                         -> (accessibility -> supervisor)*
                         -> (aggregate_findings -> supervisor)*
                         -> (code_analysis -> supervisor)? -> END

The supervisor is revisited after each node so it observes the updated
state before routing to the next one (or to END), rather than any node
ending the graph itself — the same loop-back shape a later agent (fix
agent, ...) will chain through.

Note the `?` on code_analysis: every node before it always runs, but that
one is conditional on findings existing and a source checkout being
configured (see app.agents.supervisor). The graph shape doesn't encode
that — the Supervisor's routing does.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.accessibility import accessibility_node
from app.agents.aggregate_findings import aggregate_findings_node
from app.agents.code_analysis import code_analysis_node
from app.agents.design_analysis import design_analysis_node
from app.agents.production_analysis import production_analysis_node
from app.agents.supervisor import (
    NODE_ACCESSIBILITY,
    NODE_AGGREGATE_FINDINGS,
    NODE_CODE_ANALYSIS,
    NODE_DESIGN_ANALYSIS,
    NODE_END,
    NODE_PRODUCTION_ANALYSIS,
    NODE_VISUAL_COMPARISON,
    route_after_supervisor,
    supervisor_node,
)
from app.agents.visual_comparison import visual_comparison_node
from app.graph.state import DesignQAState


def build_design_qa_graph() -> (
    CompiledStateGraph[DesignQAState, None, DesignQAState, DesignQAState]
):
    graph = StateGraph(DesignQAState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node(NODE_DESIGN_ANALYSIS, design_analysis_node)
    graph.add_node(NODE_PRODUCTION_ANALYSIS, production_analysis_node)
    graph.add_node(NODE_VISUAL_COMPARISON, visual_comparison_node)
    graph.add_node(NODE_ACCESSIBILITY, accessibility_node)
    graph.add_node(NODE_AGGREGATE_FINDINGS, aggregate_findings_node)
    graph.add_node(NODE_CODE_ANALYSIS, code_analysis_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            NODE_DESIGN_ANALYSIS: NODE_DESIGN_ANALYSIS,
            NODE_PRODUCTION_ANALYSIS: NODE_PRODUCTION_ANALYSIS,
            NODE_VISUAL_COMPARISON: NODE_VISUAL_COMPARISON,
            NODE_ACCESSIBILITY: NODE_ACCESSIBILITY,
            NODE_AGGREGATE_FINDINGS: NODE_AGGREGATE_FINDINGS,
            NODE_CODE_ANALYSIS: NODE_CODE_ANALYSIS,
            NODE_END: END,
        },
    )
    graph.add_edge(NODE_DESIGN_ANALYSIS, "supervisor")
    graph.add_edge(NODE_PRODUCTION_ANALYSIS, "supervisor")
    graph.add_edge(NODE_VISUAL_COMPARISON, "supervisor")
    graph.add_edge(NODE_ACCESSIBILITY, "supervisor")
    graph.add_edge(NODE_AGGREGATE_FINDINGS, "supervisor")
    graph.add_edge(NODE_CODE_ANALYSIS, "supervisor")

    return graph.compile()


# Built once at import time — a compiled graph is stateless/reusable
# across requests, same rationale as the get_settings()/get_figma_cache()
# singletons elsewhere in this codebase.
design_qa_graph = build_design_qa_graph()


async def run_design_qa(state: DesignQAState) -> DesignQAState:
    """Invoke the graph and return a typed state.

    ainvoke() returns a plain dict of the final state's fields (LangGraph's
    own representation, not our Pydantic model) — re-validate it back into
    DesignQAState so callers get typed attribute access.
    """
    final_state = await design_qa_graph.ainvoke(state)
    return DesignQAState.model_validate(final_state)
