"""Builds and compiles the Design QA LangGraph workflow (see
docs/architecture.md's "Runtime multi-agent workflow"). Only the Design
Analysis vertical slice exists so far:

    START -> supervisor -> (design_analysis -> supervisor)* -> END

The supervisor is revisited after design_analysis so it observes the
result before routing to END, rather than the graph exiting straight from
the agent node — the same loop-back shape later agents (production
analysis, visual comparison, ...) will chain through, each returning
control to the supervisor rather than ending the graph themselves.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.design_analysis import design_analysis_node
from app.agents.supervisor import (
    NODE_DESIGN_ANALYSIS,
    NODE_END,
    route_after_supervisor,
    supervisor_node,
)
from app.graph.state import DesignAnalysisState


def build_design_analysis_graph() -> CompiledStateGraph[
    DesignAnalysisState, None, DesignAnalysisState, DesignAnalysisState
]:
    graph = StateGraph(DesignAnalysisState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node(NODE_DESIGN_ANALYSIS, design_analysis_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {NODE_DESIGN_ANALYSIS: NODE_DESIGN_ANALYSIS, NODE_END: END},
    )
    graph.add_edge(NODE_DESIGN_ANALYSIS, "supervisor")

    return graph.compile()


# Built once at import time — a compiled graph is stateless/reusable
# across requests, same rationale as the get_settings()/get_figma_cache()
# singletons elsewhere in this codebase.
design_analysis_graph = build_design_analysis_graph()


async def run_design_analysis(state: DesignAnalysisState) -> DesignAnalysisState:
    """Invoke the graph and return a typed state.

    ainvoke() returns a plain dict of the final state's fields (LangGraph's
    own representation, not our Pydantic model) — re-validate it back into
    DesignAnalysisState so callers get typed attribute access.
    """
    final_state = await design_analysis_graph.ainvoke(state)
    return DesignAnalysisState.model_validate(final_state)
