"""Design Analysis Agent: interprets a Figma design's structure and intent
before any production implementation exists to compare it against (see
docs/architecture.md's runtime-agent table). The only judgment call here
is design interpretation — it never sees the production app, so it can't
(and doesn't try to) comment on drift; that's the Visual Comparison
Agent's job (today, app.services.reviews; a future phase moves that into
this same graph).

LLM failures (no API key, bad response shape) are deliberately not caught
here — they propagate as the same LLMNotConfiguredError/LLMResponseError
app.services.reviews already raises, so the API layer handles both the
same way. `state.error` is reserved for the Supervisor's own routing
decisions (see app.agents.supervisor), not agent failures.
"""

from typing import Any

from app.agents.types import DesignAnalysisResult
from app.graph.state import DesignAnalysisState
from app.integrations.llm.client import generate_structured

SYSTEM_PROMPT = """\
You are preparing for a production-fidelity design QA pass by analyzing a Figma design on \
its own, before any implementation exists to compare it against.

You are given a rendered image of the Figma frame and structured metadata about its node \
(name, type, layout mode, size). Interpret the design's structure and intent: what is it \
trying to achieve, what are its key components, and — since you have no code to inspect — \
which aspects would be easy for an engineer to get subtly wrong when implementing it \
(precise spacing, a non-obvious layout technique, responsive behavior that isn't visible in \
a single static render, and so on). This flags what a later comparison pass should \
scrutinize most closely.

Ground everything in what you can actually see in the image and the provided metadata."""


async def design_analysis_node(state: DesignAnalysisState) -> dict[str, Any]:
    result = await generate_structured(
        system=SYSTEM_PROMPT,
        text=_build_context_text(state.figma_node),
        images=[state.figma_screenshot],
        output_format=DesignAnalysisResult,
    )
    return {"result": result}


def _build_context_text(node: dict[str, Any]) -> str:
    box = node.get("absolute_bounding_box") or {}
    return (
        f"Figma node: name={node.get('name')!r}, type={node.get('type')!r}, "
        f"layout_mode={node.get('layout_mode')!r}, "
        f"size={box.get('width')!r} x {box.get('height')!r}\n\n"
        "Image provided: a rendered PNG of this Figma frame."
    )
