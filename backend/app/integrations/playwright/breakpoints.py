from typing import NamedTuple


class Viewport(NamedTuple):
    width: int
    height: int


STANDARD_BREAKPOINTS: dict[str, Viewport] = {
    "mobile": Viewport(375, 667),
    "tablet": Viewport(768, 1024),
    "desktop": Viewport(1440, 900),
}

# A distinct scan mode, not a fifth preset: viewport width tracks the
# Figma frame's own recorded width (resolved per-project in
# app.services.scans) instead of a fixed value, so the baseline fidelity
# comparison isn't forced to a hard-coded desktop width that may not match
# what the design was actually authored at. Height is just a normal
# browser viewport height for scrolling — full_page capture handles the
# rest, not this constant (see create_scan's docstring).
MATCH_FIGMA_BREAKPOINT = "match_figma"
MATCH_FIGMA_VIEWPORT_HEIGHT = 900
