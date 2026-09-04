"""Builds and compiles the verification graph (see docs/architecture.md's
"Runtime multi-agent workflow" — the `verify` / `before/after compare`
tail of the target flow):

    START -> recapture -> (verification)? -> END

A second graph rather than more nodes on the Design QA one, for the reason
in app.graph.verification_state's docstring: this runs later, on a page
that has been rebuilt since, from inputs the previous run recorded.

The shape is linear because there is nothing to route between — contrast
the Design QA graph, whose supervisor exists because it has real forks.
The one conditional edge here earns its place: the recapture node answers
the question itself when the page didn't change at all, and there's no
sense paying a multimodal model to compare two identical images. Same
"what hasn't been produced yet" test the Supervisor uses.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.recapture import recapture_node
from app.agents.verification import verification_node
from app.graph.verification_state import VerificationState

NODE_RECAPTURE = "recapture"
NODE_VERIFICATION = "verification"
NODE_END = "end"


def route_after_recapture(state: VerificationState) -> str:
    """Skip the judgment call when recapture already answered.

    It only does that in one case — an unchanged page — but the test is
    written as "is there a result yet" rather than "was it unchanged", so
    a future deterministic shortcut routes correctly without editing this.
    """
    return NODE_END if state.verification is not None else NODE_VERIFICATION


def build_verification_graph() -> (
    CompiledStateGraph[VerificationState, None, VerificationState, VerificationState]
):
    graph = StateGraph(VerificationState)
    graph.add_node(NODE_RECAPTURE, recapture_node)
    graph.add_node(NODE_VERIFICATION, verification_node)

    graph.add_edge(START, NODE_RECAPTURE)
    graph.add_conditional_edges(
        NODE_RECAPTURE,
        route_after_recapture,
        {NODE_VERIFICATION: NODE_VERIFICATION, NODE_END: END},
    )
    graph.add_edge(NODE_VERIFICATION, END)

    return graph.compile()


# Built once at import time, same rationale as design_qa_graph.
verification_graph = build_verification_graph()


async def run_verification(state: VerificationState) -> VerificationState:
    final_state = await verification_graph.ainvoke(state)
    return VerificationState.model_validate(final_state)
