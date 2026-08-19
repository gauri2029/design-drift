"""Production Analysis Agent: captures the live production app (see
docs/architecture.md's runtime-agent table). Unlike Design Analysis, this
is pure tool use — screenshots are deterministic (docs/principles.md #2:
"Element geometry, CSS values, navigation, screenshots → Playwright/DOM
APIs"), so this node never calls an LLM. Judgment about what the capture
*means* is the Visual Comparison Agent's job (today, app.services.reviews;
a future phase moves that into this same graph).

Capture failures (bad selector, page won't load) are deliberately not
caught here — they propagate as PlaywrightCaptureError, same as
app.services.scans already raises, so the API layer handles both the same
way. `state.error` stays reserved for the Supervisor's own routing
decisions (see app.agents.supervisor).
"""

from typing import Any

from app.graph.state import DesignQAState
from app.integrations.playwright.capture import capture_screenshot

# A plain default viewport, not a Figma-matched one: this agent's job is
# "what does production look like," independent of any particular
# comparison viewport strategy (see app.services.scans's breakpoint/
# match_figma options, which stay a scan-specific concern for now).
DEFAULT_VIEWPORT_WIDTH = 1280
DEFAULT_VIEWPORT_HEIGHT = 800


async def production_analysis_node(state: DesignQAState) -> dict[str, Any]:
    screenshot = await capture_screenshot(
        state.target_url,
        selector=state.target_selector,
        viewport_width=DEFAULT_VIEWPORT_WIDTH,
        viewport_height=DEFAULT_VIEWPORT_HEIGHT,
    )
    return {"production_screenshot": screenshot}
