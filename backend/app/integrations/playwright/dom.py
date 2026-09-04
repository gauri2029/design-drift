"""Deterministic DOM/computed-style extraction from a live page.

The other half of "inspect the real app" (docs/architecture.md's
Production Analysis row), alongside the screenshot. No LLM: an element's
tag, id, classes, accessible name, box, and computed styles are things the
browser answers exactly (docs/principles.md #2).

Why it exists: before this, the only structured evidence about the live
page came from axe-core, and axe only reports elements that *violate a
rule*. So a visual finding about the hero button had nothing to search the
repo with except words quoted out of the Visual Comparison Agent's prose.
This snapshot gives every finding the same kind of real element evidence
accessibility findings already had (see app.tools.anchors).

Deliberately not a full DOM dump. A snapshot is prompt budget and search
input, not an archive, so it keeps the elements a design finding could
plausibly be about and the styles a design finding could plausibly be
about, and truncates rather than growing without bound.
"""

from typing import Any

from playwright.async_api import Page
from pydantic import BaseModel

# Enough to cover a page's meaningful structure without turning the
# snapshot into the page itself. Extraction is in document order, so a
# truncated snapshot keeps the top of the page — which is where a Figma
# frame's content almost always is.
MAX_ELEMENTS = 250

# Visible copy is what makes an element findable in source, but a whole
# paragraph is prose, not a label. Truncation keeps anchors searchable.
MAX_TEXT_CHARS = 120

# The styles a design QA finding is actually ever about. Everything else
# (`z-index`, `overflow`, ...) is real but not something the Figma render
# can disagree with, and each extra property is paid for in every prompt
# this snapshot reaches.
CAPTURED_STYLES = (
    "color",
    "background-color",
    "font-family",
    "font-size",
    "font-weight",
    "text-align",
    "display",
    "padding",
    "margin",
    "border-radius",
)


class BoxModel(BaseModel):
    x: float
    y: float
    width: float
    height: float


class DomElement(BaseModel):
    tag: str
    element_id: str | None = None
    classes: list[str] = []
    # The element's *own* text, not its descendants' — otherwise every
    # wrapper would carry the whole page and nothing would identify
    # anything.
    text: str | None = None
    role: str | None = None
    accessible_name: str | None = None
    box: BoxModel
    styles: dict[str, str] = {}


class DomSnapshot(BaseModel):
    viewport_width: int
    viewport_height: int
    elements: list[DomElement] = []
    # True when MAX_ELEMENTS cut the page short, so a caller can say its
    # view is partial rather than quietly treating absence as evidence.
    truncated: bool = False


# Runs in the page. Kept as one expression evaluated in the browser rather
# than a locator-by-locator walk from Python: one round trip instead of
# hundreds, and `getComputedStyle` only means anything in the page anyway.
_EXTRACT_JS = """
([maxElements, maxTextChars, capturedStyles]) => {
  // Elements a design finding can be about: anything that carries its own
  // visible text, anything interactive, page landmarks, images, and
  // anything the author bothered to give an id. A bare layout div with no
  // text identifies nothing and would only crowd the snapshot out.
  const INTERESTING = new Set([
    'A','BUTTON','INPUT','SELECT','TEXTAREA','LABEL','IMG','SVG',
    'H1','H2','H3','H4','H5','H6','P','LI','TD','TH','CAPTION','FIGCAPTION',
    'HEADER','FOOTER','NAV','MAIN','ASIDE','SECTION','ARTICLE','FORM','HTML','BODY',
  ]);

  const ownText = (el) => {
    let out = '';
    for (const node of el.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) out += node.nodeValue;
    }
    return out.replace(/\\s+/g, ' ').trim().slice(0, maxTextChars);
  };

  const results = [];
  let truncated = false;

  for (const el of document.querySelectorAll('*')) {
    if (results.length >= maxElements) { truncated = true; break; }

    const text = ownText(el);
    const isInteresting = INTERESTING.has(el.tagName) || el.id || text;
    if (!isInteresting) continue;

    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    // Skip what isn't rendered. An invisible element can't be responsible
    // for a visual difference, and its styles would be misleading.
    const isDocumentRoot = el.tagName === 'HTML' || el.tagName === 'BODY';
    if (!isDocumentRoot) {
      if (rect.width === 0 || rect.height === 0) continue;
      if (style.visibility === 'hidden' || style.display === 'none') continue;
    }

    const styles = {};
    for (const property of capturedStyles) {
      const value = style.getPropertyValue(property);
      if (value) styles[property] = value.trim();
    }

    results.push({
      tag: el.tagName.toLowerCase(),
      element_id: el.id || null,
      classes: Array.from(el.classList),
      text: text || null,
      role: el.getAttribute('role'),
      accessible_name:
        el.getAttribute('aria-label') || el.getAttribute('alt') || el.getAttribute('title'),
      box: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      styles,
    });
  }

  return { elements: results, truncated };
}
"""


async def extract_dom_snapshot(
    page: Page, *, viewport_width: int, viewport_height: int
) -> DomSnapshot:
    """Snapshot the already-loaded `page`.

    Takes a Page rather than a URL on purpose: this has to describe the
    *same* render the screenshot captured, so it shares that page load
    rather than navigating again (see capture_page). A second load could
    differ — animations, lazy content, ads — and then the DOM would be
    evidence about a page nobody looked at.
    """
    raw: dict[str, Any] = await page.evaluate(
        _EXTRACT_JS, [MAX_ELEMENTS, MAX_TEXT_CHARS, list(CAPTURED_STYLES)]
    )
    return DomSnapshot(
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        elements=[DomElement.model_validate(element) for element in raw["elements"]],
        truncated=bool(raw["truncated"]),
    )
