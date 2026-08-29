"""Extract deterministic search anchors from what the inspection agents
already observed about the live page.

No LLM: pulling ids, class names, accessible names and visible text out of
DOM evidence is parsing, not judgment (docs/principles.md #2). These
anchors are what turns "the CTA button is too narrow" into something a
content search can actually look for — the weak link in the paths-only
version of the Code Analysis Agent.

Anchor quality varies by where a finding came from, which is why kind is
kept alongside value:

- Accessibility findings carry real DOM evidence, because axe-core reports
  the offending element's `html` and CSS `target` per violation. Ids and
  aria-labels from there are strong, near-unique signals.
- Visual findings are LLM prose, so the only deterministic thing to pull
  is quoted literals ("Get started") — the model tends to quote visible
  copy, and visible copy is exactly what appears in source.

Nothing here reads the repo; that's app.tools.repo_search's job.
"""

import re
from collections.abc import Iterable, Sequence
from enum import StrEnum
from html.parser import HTMLParser

from pydantic import BaseModel

from app.integrations.axe.types import AccessibilityReport

# Weights feed candidate ranking (see repo_search.search_corpus). Ordered
# by how close to unique the signal usually is: an id or an aria-label
# generally identifies one element, whereas a class is routinely shared
# and utility-CSS class names ("flex", "px-4") are shared by everything.
_ANCHOR_WEIGHTS = {
    "id": 5,
    "aria_label": 4,
    "text": 3,
    "class": 2,
    # Weaker than a quoted literal: a title-case run is inferred from
    # prose rather than reported as a string, so it's likelier to be
    # incidental. Still worth searching — section headings ("Schedule of
    # Events") are usually named this way in findings and appear verbatim
    # in markup.
    "phrase": 2,
    # Weakest, and deliberately so: a tag name identifies a file, not a
    # place in it. Its job is to stop whole-document rules (html-has-lang,
    # landmark-one-main) from having no anchor at all.
    "tag": 1,
}

# Below this, a token matches far too much to locate anything.
MIN_ANCHOR_LENGTH = 3

# Tokens so common in web codebases that they'd match most files. This is
# a cheap first pass only — the real defense against non-discriminative
# anchors is the document-frequency filter in repo_search, which adapts to
# the codebase at hand instead of guessing at a list up front.
_GENERIC_TOKENS = frozenset(
    {
        "active",
        "block",
        "body",
        "col",
        "container",
        "content",
        "disabled",
        "div",
        "flex",
        "grid",
        "hidden",
        "html",
        "inner",
        "item",
        "large",
        "left",
        "main",
        "open",
        "outer",
        "page",
        "right",
        "row",
        "section",
        "small",
        "span",
        "text",
        "wrapper",
    }
)

_SELECTOR_TOKEN = re.compile(r"([#.])([A-Za-z_][\w-]*)")
# A selector that is nothing but a bare tag name, e.g. axe's target for
# html-has-lang ("html") or landmark-one-main.
_BARE_TAG_SELECTOR = re.compile(r"^\s*([a-zA-Z][a-zA-Z0-9]*)\s*$")
# Only tags that appear once and structure the document. A bare "div" or
# "span" target would anchor on nothing useful.
_STRUCTURAL_TAGS = frozenset({"html", "body", "main", "header", "footer", "nav"})

# Decoration the model adds when transcribing a rendered label — "Links ->"
# is a CSS arrow next to the word "Links", and only "Links" is in source.
_TEXT_DECORATION = "\u2192\u27f6\u00bb\u203a\u2026<>-=*_:;,.!?\u00a0 \t"

# Title-case runs in unquoted prose, e.g. "Schedule of Events". Findings
# name sections this way constantly without quoting them, and section
# names appear verbatim in markup.
_TITLE_CASE_PHRASE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+(?:of|and|the|for|to|in|on|at|from|a|an|with)?\s*[A-Z][a-z]+)+)"
)
# Sentences start with a capital, so a leading article is usually grammar
# rather than part of the name.
_PHRASE_LEAD_WORDS = ("The ", "A ", "An ", "This ", "These ", "Those ", "Its ")
# Quoted literals in LLM prose. Deliberately bounded: a very long "quote"
# is a sentence being quoted, not a UI string worth searching for.
_QUOTED_LITERAL = re.compile(r"[\"'`]([^\"'`\n]{3,60})[\"'`]")


class AnchorKind(StrEnum):
    ID = "id"
    ARIA_LABEL = "aria_label"
    TEXT = "text"
    CLASS = "class"
    PHRASE = "phrase"
    TAG = "tag"


class Anchor(BaseModel):
    kind: AnchorKind
    value: str

    @property
    def weight(self) -> int:
        return _ANCHOR_WEIGHTS[self.kind.value]

    def matches(self, line: str) -> bool:
        """Whether this anchor appears in one line of source.

        Case-sensitive except for TEXT/PHRASE/TAG: ids and class names are
        case-sensitive in HTML/CSS and in every framework's markup, but
        visible copy routinely differs in case between the rendered page
        and the source (CSS `text-transform`, or a template that
        capitalizes).
        """
        if self.kind is AnchorKind.TAG:
            # The angle bracket matters: it matches the element's markup
            # rather than every prose mention of the word "html".
            return f"<{self.value}" in line.lower()
        if self.kind in (AnchorKind.TEXT, AnchorKind.PHRASE):
            return self.value.lower() in line.lower()
        return self.value in line


class _ElementParser(HTMLParser):
    """Pulls ids/classes/aria-labels/text out of an axe `html` fragment.

    stdlib rather than a parser dependency: axe hands back a small,
    well-formed fragment for one element, which is squarely within what
    HTMLParser handles.
    """

    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.classes: list[str] = []
        self.aria_labels: list[str] = []
        self.texts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if not value:
                continue
            if name == "id":
                self.ids.append(value)
            elif name == "class":
                self.classes.extend(value.split())
            elif name in ("aria-label", "title", "alt"):
                self.aria_labels.append(value)

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.texts.append(text)


def extract_anchors(
    *,
    texts: Sequence[str] = (),
    accessibility_report: AccessibilityReport | None = None,
    violation_ids: Sequence[str] | None = None,
    target_selector: str | None = None,
) -> list[Anchor]:
    """Collect anchors, strongest kind first.

    `violation_ids` narrows which axe violations contribute DOM evidence —
    passing the ids behind one finding keeps that finding's search from
    being polluted by unrelated elements elsewhere on the page. Omit it to
    use every violation.
    """
    collected: list[Anchor] = []

    for selector in filter(None, [target_selector]):
        collected.extend(_from_selector(selector))

    if accessibility_report is not None:
        for violation in accessibility_report.violations:
            if violation_ids is not None and violation.id not in violation_ids:
                continue
            for node in violation.nodes:
                for selector in node.target:
                    collected.extend(_from_selector(selector))
                if node.html:
                    collected.extend(_from_html(node.html))

    for text in texts:
        collected.extend(
            Anchor(kind=AnchorKind.TEXT, value=_normalize_text(literal))
            for literal in _QUOTED_LITERAL.findall(text)
        )
        collected.extend(Anchor(kind=AnchorKind.PHRASE, value=phrase) for phrase in _phrases(text))

    return _deduplicate(anchor for anchor in collected if _is_usable(anchor))


def _from_selector(selector: str) -> list[Anchor]:
    kinds = {"#": AnchorKind.ID, ".": AnchorKind.CLASS}
    anchors = [
        Anchor(kind=kinds[prefix], value=name)
        for prefix, name in _SELECTOR_TOKEN.findall(selector)
    ]
    if anchors:
        return anchors

    # No id or class to go on. If the whole selector is a structural tag,
    # fall back to anchoring on the element itself — that's the difference
    # between pointing at the right file and returning no_match for
    # document-level rules.
    bare_tag = _BARE_TAG_SELECTOR.match(selector)
    if bare_tag and bare_tag.group(1).lower() in _STRUCTURAL_TAGS:
        return [Anchor(kind=AnchorKind.TAG, value=bare_tag.group(1).lower())]
    return []


def _normalize_text(value: str) -> str:
    return value.strip(_TEXT_DECORATION)


def _phrases(text: str) -> list[str]:
    found: list[str] = []
    for phrase in _TITLE_CASE_PHRASE.findall(text):
        cleaned = phrase.strip()
        for lead in _PHRASE_LEAD_WORDS:
            if cleaned.startswith(lead):
                cleaned = cleaned[len(lead) :]
                break
        # One capitalized word left is just a word, not a section name.
        if len(cleaned.split()) >= 2:
            found.append(cleaned)
    return found


def _from_html(html: str) -> list[Anchor]:
    parser = _ElementParser()
    parser.feed(html)
    parser.close()
    return [
        *(Anchor(kind=AnchorKind.ID, value=value) for value in parser.ids),
        *(Anchor(kind=AnchorKind.ARIA_LABEL, value=value) for value in parser.aria_labels),
        *(Anchor(kind=AnchorKind.TEXT, value=_normalize_text(value)) for value in parser.texts),
        *(Anchor(kind=AnchorKind.CLASS, value=value) for value in parser.classes),
    ]


def _is_usable(anchor: Anchor) -> bool:
    if len(anchor.value) < MIN_ANCHOR_LENGTH:
        return False
    # Ids and accessible names stay even when they look generic — they're
    # specific enough that a false positive costs little, and dropping a
    # real id would lose the best signal available.
    if anchor.kind in (AnchorKind.CLASS, AnchorKind.TEXT, AnchorKind.PHRASE):
        return anchor.value.lower() not in _GENERIC_TOKENS
    return True


def _deduplicate(anchors: Iterable[Anchor]) -> list[Anchor]:
    seen: dict[tuple[str, str], Anchor] = {}
    for anchor in anchors:
        seen.setdefault((anchor.kind.value, anchor.value), anchor)
    return sorted(seen.values(), key=lambda anchor: (-anchor.weight, anchor.value))
