"""Unit tests for app.tools.anchors — pure parsing, no LLM/DB/filesystem."""

import pytest

from app.integrations.axe.types import AccessibilityReport, AxeNode, AxeViolation
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
