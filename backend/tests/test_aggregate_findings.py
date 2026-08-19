"""Unit tests for app.agents.aggregate_findings — pure merge/sort logic,
no LLM, no browser, no DB (the node is deterministic by design; see its
module docstring).
"""

from uuid import uuid4

import pytest

from app.agents.aggregate_findings import aggregate_findings_node
from app.agents.types import (
    AccessibilityInterpretation,
    AccessibilityIssue,
    AccessibilityPriority,
    FindingPriority,
    FindingSource,
)
from app.graph.state import DesignQAState
from app.integrations.llm.types import (
    DesignFinding,
    FindingCategory,
    FindingSeverity,
    VisualReviewResult,
)


def _state(
    *,
    visual: VisualReviewResult | None = None,
    accessibility: AccessibilityInterpretation | None = None,
) -> DesignQAState:
    return DesignQAState(
        project_id=uuid4(),
        figma_node={"name": "Hero"},
        figma_screenshot=b"fake-png",
        target_url="https://example.com",
        visual_comparison=visual,
        accessibility_interpretation=accessibility,
    )


def _visual_finding(
    severity: FindingSeverity, title: str = "Button is narrower than designed"
) -> DesignFinding:
    return DesignFinding(
        category=FindingCategory.SPACING,
        severity=severity,
        title=title,
        description="Figma shows a wider button; production renders narrower.",
        evidence="The diff image highlights the button edge.",
        likely_area="the primary call-to-action button",
    )


def _visual(*findings: DesignFinding, material_drift_detected: bool = True) -> VisualReviewResult:
    return VisualReviewResult(
        material_drift_detected=material_drift_detected,
        summary="Some drift.",
        findings=list(findings),
    )


def _accessibility(*issues: AccessibilityIssue) -> AccessibilityInterpretation:
    return AccessibilityInterpretation(summary="Some issues.", most_important_issues=list(issues))


def _issue(
    priority: AccessibilityPriority, violation_id: str = "color-contrast"
) -> AccessibilityIssue:
    return AccessibilityIssue(
        violation_id=violation_id,
        user_impact="Low-vision users may not be able to read the label.",
        priority=priority,
    )


def _aggregate(state: DesignQAState):
    return aggregate_findings_node(state)["aggregated_findings"]


def test_merges_findings_from_both_agents() -> None:
    result = _aggregate(
        _state(
            visual=_visual(_visual_finding(FindingSeverity.MAJOR)),
            accessibility=_accessibility(_issue(AccessibilityPriority.HIGH)),
        )
    )

    assert result.problems_found is True
    assert len(result.findings) == 2
    assert {finding.source for finding in result.findings} == {
        FindingSource.VISUAL_COMPARISON,
        FindingSource.ACCESSIBILITY,
    }


@pytest.mark.parametrize(
    ("severity", "expected_priority"),
    [
        # critical and major both collapse to HIGH — the documented lossy
        # edge of the mapping, which is why original_severity is kept.
        (FindingSeverity.CRITICAL, FindingPriority.HIGH),
        (FindingSeverity.MAJOR, FindingPriority.HIGH),
        (FindingSeverity.MINOR, FindingPriority.MEDIUM),
        (FindingSeverity.COSMETIC, FindingPriority.LOW),
    ],
)
def test_maps_visual_severity_onto_the_shared_priority_scale(
    severity: FindingSeverity, expected_priority: FindingPriority
) -> None:
    result = _aggregate(_state(visual=_visual(_visual_finding(severity))))

    assert result.findings[0].priority == expected_priority
    # The agent's own word survives the normalization.
    assert result.findings[0].original_severity == severity.value


@pytest.mark.parametrize(
    "priority",
    [AccessibilityPriority.HIGH, AccessibilityPriority.MEDIUM, AccessibilityPriority.LOW],
)
def test_accessibility_priority_passes_through_unchanged(
    priority: AccessibilityPriority,
) -> None:
    result = _aggregate(_state(accessibility=_accessibility(_issue(priority))))

    assert result.findings[0].priority.value == priority.value
    assert result.findings[0].original_severity == priority.value


def test_orders_findings_highest_priority_first_across_agents() -> None:
    result = _aggregate(
        _state(
            # Deliberately supplied lowest-first, and visual-before-a11y,
            # so a no-op sort would fail this.
            visual=_visual(_visual_finding(FindingSeverity.COSMETIC, title="cosmetic-visual")),
            accessibility=_accessibility(_issue(AccessibilityPriority.HIGH, "high-a11y")),
        )
    )

    assert [finding.title for finding in result.findings] == ["high-a11y", "cosmetic-visual"]


def test_sort_is_stable_within_one_priority() -> None:
    result = _aggregate(
        _state(
            visual=_visual(
                _visual_finding(FindingSeverity.CRITICAL, title="first"),
                _visual_finding(FindingSeverity.MAJOR, title="second"),
            )
        )
    )

    # Both are HIGH; the agent ordered them most-severe first, and that
    # ordering must survive.
    assert [finding.title for finding in result.findings] == ["first", "second"]


def test_carries_likely_area_for_visual_findings_only() -> None:
    result = _aggregate(
        _state(
            visual=_visual(_visual_finding(FindingSeverity.MAJOR)),
            accessibility=_accessibility(_issue(AccessibilityPriority.HIGH)),
        )
    )

    by_source = {finding.source: finding for finding in result.findings}
    assert by_source[FindingSource.VISUAL_COMPARISON].likely_area is not None
    assert by_source[FindingSource.ACCESSIBILITY].likely_area is None


def test_no_findings_and_no_drift_means_no_problems() -> None:
    result = _aggregate(
        _state(
            visual=_visual(material_drift_detected=False),
            accessibility=_accessibility(),
        )
    )

    assert result.problems_found is False
    assert result.findings == []


def test_material_drift_counts_as_a_problem_even_with_no_itemized_findings() -> None:
    # The Visual Comparison Agent's overall verdict is a judgment in its
    # own right — it shouldn't be silently dropped just because it didn't
    # enumerate anything.
    result = _aggregate(_state(visual=_visual(material_drift_detected=True)))

    assert result.problems_found is True
    assert result.findings == []
