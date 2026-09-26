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

from collections.abc import AsyncIterator

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.accessibility import accessibility_node
from app.agents.aggregate_findings import aggregate_findings_node
from app.agents.code_analysis import code_analysis_node
from app.agents.design_analysis import design_analysis_node
from app.agents.fix import fix_node
from app.agents.production_analysis import production_analysis_node
from app.agents.supervisor import (
    NODE_ACCESSIBILITY,
    NODE_AGGREGATE_FINDINGS,
    NODE_CODE_ANALYSIS,
    NODE_DESIGN_ANALYSIS,
    NODE_END,
    NODE_FIX,
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
    graph.add_node(NODE_FIX, fix_node)

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
            NODE_FIX: NODE_FIX,
            NODE_END: END,
        },
    )
    graph.add_edge(NODE_DESIGN_ANALYSIS, "supervisor")
    graph.add_edge(NODE_PRODUCTION_ANALYSIS, "supervisor")
    graph.add_edge(NODE_VISUAL_COMPARISON, "supervisor")
    graph.add_edge(NODE_ACCESSIBILITY, "supervisor")
    graph.add_edge(NODE_AGGREGATE_FINDINGS, "supervisor")
    graph.add_edge(NODE_CODE_ANALYSIS, "supervisor")
    graph.add_edge(NODE_FIX, "supervisor")

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


async def stream_design_qa(state: DesignQAState) -> AsyncIterator[tuple[str, DesignQAState]]:
    """Yield `(node_name, state_so_far)` as each node finishes.

    Same graph and same result as run_design_qa — this only exposes the
    steps rather than waiting for all of them. A run launches a browser and
    makes several LLM calls, so it takes tens of seconds, and a single
    blocking request spends all of that saying nothing.

    Two stream modes at once: "updates" names the node that just ran (the
    only place LangGraph reports *which* one it was), and "values" carries
    the accumulated state, which is what the caller has to persist at the
    end. Neither alone gives both halves.
    """
    latest = state
    pending: list[str] = []

    async for mode, chunk in design_qa_graph.astream(state, stream_mode=["updates", "values"]):
        if mode == "updates":
            # One dict per superstep, keyed by node name. The supervisor is
            # routing rather than doing work, so it isn't worth reporting.
            pending.extend(name for name in chunk if name != "supervisor")
        elif mode == "values":
            latest = DesignQAState.model_validate(chunk)
            # Emitted only once the state that goes with them has arrived,
            # so a consumer never sees a node reported as done before its
            # output exists.
            for name in pending:
                yield name, latest
            pending.clear()
