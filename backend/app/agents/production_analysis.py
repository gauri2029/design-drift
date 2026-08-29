"""Production Analysis Agent: captures the live production app (see
docs/architecture.md's runtime-agent table). Unlike Design Analysis, this
is pure tool use — screenshots are deterministic (docs/principles.md #2:
"Element geometry, CSS values, navigation, screenshots → Playwright/DOM
APIs"), so this node never calls an LLM. Judgment about what the capture
*means* is the Visual Comparison Agent's job.

The capture width tracks the Figma frame's own width (the same
match_figma rule scans use — see
app.integrations.playwright.breakpoints.match_figma_viewport). It has to:
this capture exists purely to be diffed against that Figma render two
nodes later, and capturing 1280px-wide production against a 1400px-wide
design manufactures layout drift that nothing in the target app caused.
The Visual Comparison Agent then reports that as a real finding, which is
worse than useless — it's a confident, wrong answer.

Capture failures (bad selector, page won't load) are deliberately not
caught here — they propagate as PlaywrightCaptureError, same as
app.services.scans already raises, so the API layer handles both the same
way. `state.error` stays reserved for the Supervisor's own routing
decisions (see app.agents.supervisor).
"""

from typing import Any

from app.graph.state import DesignQAState
from app.integrations.playwright.breakpoints import Viewport, match_figma_viewport
from app.integrations.playwright.capture import capture_screenshot

# Used only when the Figma node records no width — rare, since Design
# Analysis has already run by this point. A capture at a plain desktop
# width is still worth having; refusing to capture at all would lose the
# accessibility scan and every other downstream finding too.
FALLBACK_VIEWPORT = Viewport(1280, 800)


async def production_analysis_node(state: DesignQAState) -> dict[str, Any]:
    viewport = match_figma_viewport(state.figma_node) or FALLBACK_VIEWPORT

    screenshot = await capture_screenshot(
        state.target_url,
        selector=state.target_selector,
        viewport_width=viewport.width,
        viewport_height=viewport.height,
    )
    return {"production_screenshot": screenshot}
