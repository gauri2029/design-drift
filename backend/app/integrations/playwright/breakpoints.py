from typing import Any, NamedTuple


class Viewport(NamedTuple):
    width: int
    height: int


STANDARD_BREAKPOINTS: dict[str, Viewport] = {
    "mobile": Viewport(375, 667),
    "tablet": Viewport(768, 1024),
    "desktop": Viewport(1440, 900),
}

# A distinct scan mode, not a fifth preset: viewport width tracks the
# Figma frame's own recorded width (see match_figma_viewport) instead of
# a fixed value, so the baseline fidelity comparison isn't forced to a
# hard-coded desktop width that may not match
# what the design was actually authored at. Height is just a normal
# browser viewport height for scrolling — full_page capture handles the
# rest, not this constant (see create_scan's docstring).
MATCH_FIGMA_BREAKPOINT = "match_figma"
MATCH_FIGMA_VIEWPORT_HEIGHT = 900


def match_figma_viewport(figma_node: dict[str, Any]) -> Viewport | None:
    """Viewport whose width tracks a Figma node's own recorded width.

    Returns None when the node has no recorded width, leaving the caller
    to decide whether that's fatal (a scan explicitly asked for
    match_figma) or merely a fallback (the Design QA graph still wants a
    capture).

    Height is deliberately *not* matched to the Figma frame: full_page
    capture is what gets the page's real height, so this only needs to be
    a normal browser viewport height for scrolling.
    """
    # figma_node is stored via FigmaNode.model_dump(mode="json") with no
    # by_alias=True (see app.services.projects), so keys here are the
    # model's plain field names (snake_case), not the camelCase aliases
    # the API re-applies on the way out in ProjectRead responses.
    bounding_box = figma_node.get("absolute_bounding_box")
    width = bounding_box.get("width") if bounding_box else None
    if width is None:
        return None
    # Figma reports width as a float. round(), not int() — int() truncates
    # toward zero and would silently shave a fractional pixel off the
    # intended width.
    return Viewport(round(width), MATCH_FIGMA_VIEWPORT_HEIGHT)
