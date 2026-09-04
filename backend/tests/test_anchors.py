"""Unit tests for app.tools.anchors — pure parsing, no LLM/DB/filesystem."""

import pytest

from app.integrations.axe.types import AccessibilityReport, AxeNode, AxeViolation
from app.integrations.playwright.dom import DomElement, DomSnapshot
from app.tools.anchors import Anchor, AnchorKind, extract_anchors


def _report(
    *, html: str | None = None, target: list[str] | None = None, rule: str = "color-contrast"
):
    return AccessibilityReport(
        violations=[
            AxeViolation(
                id=rule,
                description="d",
                help="h",
                helpUrl="https://example.com",
                nodes=[AxeNode(target=target or [], html=html)],
            )
        ],
        violation_count=1,
    )


def _values(anchors: list[Anchor], kind: AnchorKind) -> set[str]:
    return {anchor.value for anchor in anchors if anchor.kind is kind}


def test_extracts_id_class_label_and_text_from_dom_evidence() -> None:
    anchors = extract_anchors(
        accessibility_report=_report(
            html='<button id="hero-cta" class="btn btn-primary" aria-label="Start free trial">'
            "Get started</button>"
        )
    )

    assert _values(anchors, AnchorKind.ID) == {"hero-cta"}
    assert _values(anchors, AnchorKind.CLASS) == {"btn", "btn-primary"}
    assert _values(anchors, AnchorKind.ARIA_LABEL) == {"Start free trial"}
    assert _values(anchors, AnchorKind.TEXT) == {"Get started"}


def test_extracts_ids_and_classes_from_css_target_selectors() -> None:
    anchors = extract_anchors(
        accessibility_report=_report(target=["#main-nav > .nav-link.is-current"])
    )

    assert _values(anchors, AnchorKind.ID) == {"main-nav"}
    assert _values(anchors, AnchorKind.CLASS) == {"nav-link", "is-current"}


def test_extracts_quoted_literals_from_finding_prose() -> None:
    anchors = extract_anchors(
        texts=['The button labelled "Start free trial" is narrower than designed.']
    )

    assert _values(anchors, AnchorKind.TEXT) == {"Start free trial"}


def test_includes_the_projects_target_selector() -> None:
    anchors = extract_anchors(target_selector="#hero .cta-button")

    assert _values(anchors, AnchorKind.ID) == {"hero"}
    assert _values(anchors, AnchorKind.CLASS) == {"cta-button"}


def test_narrows_dom_evidence_to_the_named_violation() -> None:
    report = AccessibilityReport(
        violations=[
            AxeViolation(
                id="color-contrast",
                description="d",
                help="h",
                helpUrl="https://example.com",
                nodes=[AxeNode(target=["#wanted"])],
            ),
            AxeViolation(
                id="image-alt",
                description="d",
                help="h",
                helpUrl="https://example.com",
                nodes=[AxeNode(target=["#unwanted"])],
            ),
        ],
        violation_count=2,
    )

    anchors = extract_anchors(accessibility_report=report, violation_ids=["color-contrast"])

    assert _values(anchors, AnchorKind.ID) == {"wanted"}


def test_empty_violation_ids_means_no_dom_evidence() -> None:
    # Visual findings pass [] — they have no link to any axe violation, so
    # borrowing another element's DOM would be noise, not evidence.
    anchors = extract_anchors(accessibility_report=_report(target=["#hero"]), violation_ids=[])

    assert anchors == []


def test_drops_generic_class_names_and_short_tokens() -> None:
    anchors = extract_anchors(
        accessibility_report=_report(html='<div class="container row btn-primary xy">text</div>')
    )

    # "container"/"row" are stoplisted, "xy" is under MIN_ANCHOR_LENGTH.
    assert _values(anchors, AnchorKind.CLASS) == {"btn-primary"}


def test_keeps_generic_looking_ids() -> None:
    # An id is specific enough to be worth searching even when the word
    # itself is common — losing a real id costs more than a false positive.
    anchors = extract_anchors(accessibility_report=_report(target=["#main"]))

    assert _values(anchors, AnchorKind.ID) == {"main"}


def test_deduplicates_repeated_evidence() -> None:
    anchors = extract_anchors(
        accessibility_report=_report(
            html='<a class="nav-link" href="#">Home</a>', target=[".nav-link"]
        )
    )

    assert [anchor.value for anchor in anchors].count("nav-link") == 1


def test_orders_strongest_kinds_first() -> None:
    anchors = extract_anchors(
        accessibility_report=_report(
            html='<button id="cta" class="btn-primary" aria-label="Buy now">Purchase</button>'
        )
    )

    assert [anchor.kind for anchor in anchors] == [
        AnchorKind.ID,
        AnchorKind.ARIA_LABEL,
        AnchorKind.TEXT,
        AnchorKind.CLASS,
    ]


def test_no_evidence_yields_no_anchors() -> None:
    assert extract_anchors(texts=["The spacing feels slightly off."]) == []


@pytest.mark.parametrize(
    ("kind", "line", "expected"),
    [
        # Ids/classes are case-sensitive in markup and CSS.
        (AnchorKind.CLASS, 'class="btn-primary"', True),
        (AnchorKind.CLASS, 'class="BTN-PRIMARY"', False),
        # Visible copy routinely differs in case between page and source
        # (CSS text-transform, or a template that capitalizes).
        (AnchorKind.TEXT, "<span>get started</span>", True),
    ],
)
def test_match_case_sensitivity_depends_on_kind(
    kind: AnchorKind, line: str, expected: bool
) -> None:
    value = "btn-primary" if kind is AnchorKind.CLASS else "Get Started"

    assert Anchor(kind=kind, value=value).matches(line) is expected


def test_falls_back_to_a_tag_anchor_for_document_level_rules() -> None:
    # axe targets the bare <html> element for rules like html-has-lang.
    # Without this, such findings have no anchor at all and can only ever
    # come back no_match — even though the answer is line 2 of the markup.
    anchors = extract_anchors(accessibility_report=_report(target=["html"]))

    assert [(a.kind, a.value) for a in anchors] == [(AnchorKind.TAG, "html")]


def test_ignores_bare_tags_that_identify_nothing() -> None:
    # "div" appears everywhere; anchoring on it would rank noise.
    assert extract_anchors(accessibility_report=_report(target=["div"])) == []


def test_tag_anchor_matches_markup_not_prose() -> None:
    tag = Anchor(kind=AnchorKind.TAG, value="html")

    assert tag.matches("<html lang='en'>") is True
    assert tag.matches("  <HTML>") is True
    # The word in a comment or a filename must not count as the element.
    assert tag.matches("// see index.html for details") is False


def test_strips_decoration_from_quoted_labels() -> None:
    # The model transcribes a rendered label including a CSS arrow; only
    # the word itself is in the markup.
    anchors = extract_anchors(texts=["The button reads 'Links ->' instead of 'Register ->'."])

    assert _values(anchors, AnchorKind.TEXT) == {"Links", "Register"}


def test_extracts_unquoted_title_case_section_names() -> None:
    # Findings name sections without quoting them, and the name appears
    # verbatim in markup.
    anchors = extract_anchors(
        texts=["The Schedule of Events list shows only 5 items instead of 7."]
    )

    assert _values(anchors, AnchorKind.PHRASE) == {"Schedule of Events"}


def test_phrase_extraction_drops_a_leading_article() -> None:
    # "The" here is sentence grammar, not part of the section's name.
    anchors = extract_anchors(texts=["The Register Now block is missing."])

    assert _values(anchors, AnchorKind.PHRASE) == {"Register Now"}


def test_a_single_capitalized_word_is_not_a_phrase() -> None:
    # One capitalized word is just a word — usually the sentence's first.
    assert extract_anchors(texts=["Production renders this differently."]) == []


def test_phrase_anchors_rank_below_quoted_literals() -> None:
    # A quoted string was reported verbatim; a title-case run was inferred
    # from prose, so it should carry less ranking weight.
    quoted = Anchor(kind=AnchorKind.TEXT, value="Get started")
    phrase = Anchor(kind=AnchorKind.PHRASE, value="Schedule of Events")

    assert quoted.weight > phrase.weight


# --- DOM-backed anchors for visual findings --------------------------------
#
# The gap this closed: before the DOM snapshot, a visual finding could only
# contribute the words in its own prose, while an accessibility finding got
# real element evidence from axe. These cover the lookup that made those
# two symmetric.


def _element(**overrides) -> DomElement:
    defaults = {
        "tag": "a",
        "element_id": "hero-cta",
        "classes": ["cta", "button-primary"],
        "text": "Links",
        "box": {"x": 0, "y": 0, "width": 100, "height": 40},
    }
    return DomElement.model_validate({**defaults, **overrides})


def _snapshot(*elements: DomElement) -> DomSnapshot:
    return DomSnapshot(viewport_width=1400, viewport_height=900, elements=list(elements))


def test_a_quoted_literal_resolves_to_the_real_element_behind_it() -> None:
    """A visual finding naming a button now yields that button's id and
    classes — the same kind of evidence axe gives an accessibility one."""
    anchors = extract_anchors(
        texts=["The hero button label reads 'Links' instead of 'Register Now'."],
        dom_snapshot=_snapshot(_element()),
    )

    values = {(anchor.kind.value, anchor.value) for anchor in anchors}
    assert ("id", "hero-cta") in values
    assert ("class", "button-primary") in values
    # The words are still anchors too — source often contains the copy
    # even when it doesn't contain the id.
    assert ("text", "Links") in values


def test_a_title_case_section_name_resolves_through_the_dom_too() -> None:
    anchors = extract_anchors(
        texts=["The Schedule of Events list does not match the design."],
        dom_snapshot=_snapshot(
            _element(element_id="schedule", classes=["agenda"], text="Schedule of Events", tag="h2")
        ),
    )

    values = {(anchor.kind.value, anchor.value) for anchor in anchors}
    assert ("id", "schedule") in values
    assert ("class", "agenda") in values


def test_copy_the_page_repeats_is_dropped_rather_than_anchoring_on_all_of_it() -> None:
    """ "Read more" on seven buttons names none of them; anchoring on every
    one would drag half the page's markup into the search."""
    repeated = [
        _element(element_id=f"more-{index}", classes=["repeated"], text="Read more")
        for index in range(7)
    ]

    anchors = extract_anchors(
        texts=["The 'Read more' links are misaligned."], dom_snapshot=_snapshot(*repeated)
    )

    assert not any(anchor.kind is AnchorKind.ID for anchor in anchors)


def test_a_finding_naming_nothing_on_the_page_still_yields_no_element_anchors() -> None:
    """No fuzzy matching: either the page contains that copy or it
    doesn't. Guessing at near-misses is what produces confident noise."""
    anchors = extract_anchors(
        texts=["The 'Download the brochure' button is missing."],
        dom_snapshot=_snapshot(_element()),
    )

    assert not any(anchor.kind in (AnchorKind.ID, AnchorKind.CLASS) for anchor in anchors)


def test_an_accessible_name_matches_where_there_is_no_visible_text() -> None:
    anchors = extract_anchors(
        texts=["The 'CNS logo' image is the wrong size."],
        dom_snapshot=_snapshot(
            _element(
                tag="img", element_id="logo", classes=[], text=None, accessible_name="CNS logo"
            )
        ),
    )

    assert ("id", "logo") in {(anchor.kind.value, anchor.value) for anchor in anchors}
