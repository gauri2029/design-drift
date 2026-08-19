"""Visual Comparison Agent: Figma vs. production → structured drift
findings (see docs/architecture.md's runtime-agent table: "image diffing,
multimodal LLM"). Two steps in one node rather than two nodes, because
they're not independently useful — the LLM judgment call needs the diff
image the pixel-diff step produces, so there's no meaningful point to
route back through the Supervisor between them (contrast Production
Analysis, which is deterministic-only, and Design Analysis, which is
LLM-only).

Reuses VisualReviewResult (app.integrations.llm.types) — the same
judgment task app.services.reviews already does for a Scan — but the
system prompt here drops the accessibility context that module adds,
since the Accessibility Agent isn't wired into this graph yet.
"""

from typing import Any

from app.graph.state import DesignQAState
from app.integrations.imaging.compare import compare_images
from app.integrations.imaging.types import ComparisonResult
from app.integrations.llm.client import generate_structured
from app.integrations.llm.types import VisualReviewResult

SYSTEM_PROMPT = """\
You review a web page's visual implementation against its Figma design.

You are given three images, always in this order: the Figma reference render \
(expected), a screenshot of the live production page (actual), and a pixel-diff \
visualization highlighting where they differ. You are also given a deterministic \
pixel-mismatch percentage from image diffing.

The pixel-mismatch percentage alone cannot tell real design drift apart from \
inconsequential differences — antialiasing, font rendering, or (when the sizes \
genuinely differ) the padding introduced by comparing a small element against a \
larger canvas. Your job is that judgment call: look at the actual images and decide \
whether the difference is a real, material design problem, and if so, describe \
specifically what's wrong.

Ground every finding in what you can actually see in the images. You have no access \
to source code, so don't speculate about implementation causes — describe what's \
wrong visually and, if you can tell, which part of the UI is responsible."""


async def visual_comparison_node(state: DesignQAState) -> dict[str, Any]:
    assert state.production_screenshot is not None  # supervisor only routes here once set

    comparison_result, diff_png = compare_images(
        state.figma_screenshot, state.production_screenshot
    )

    result = await generate_structured(
        system=SYSTEM_PROMPT,
        text=_build_context_text(comparison_result),
        images=[state.figma_screenshot, state.production_screenshot, diff_png],
        output_format=VisualReviewResult,
    )

    return {
        "comparison_result": comparison_result,
        "diff_screenshot": diff_png,
        "visual_comparison": result,
    }


def _build_context_text(comparison: ComparisonResult) -> str:
    return (
        f"Deterministic pixel diff: {comparison.mismatch_percentage:.2f}% mismatch, "
        f"dimensions_match={comparison.dimensions_match}, "
        f"expected_dimensions={comparison.expected_dimensions.model_dump()}, "
        f"actual_dimensions={comparison.actual_dimensions.model_dump()}\n\n"
        "Images provided, in order: (1) Figma reference render — the expected design, "
        "(2) production screenshot — what the live app actually shows, "
        "(3) pixel-diff visualization — differing pixels highlighted."
    )
