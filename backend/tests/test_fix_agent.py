"""Unit tests for app.agents.fix — the routing decision and the
deterministic patch verification. No LLM: the one call this node makes is
covered end to end in test_design_analysis_graph.py.
"""

from pathlib import Path
from uuid import uuid4

import pytest

from app.agents.fix import _build_context_text, _verify
from app.agents.supervisor import NODE_END, NODE_FIX, route_after_supervisor
from app.agents.types import (
    AccessibilityInterpretation,
    AggregatedFinding,
    AggregatedFindings,
    CodeAnalysisResult,
    DesignAnalysisResult,
    FindingLocation,
    FindingPriority,
    FindingSource,
    FixConfidence,
    FixResult,
    Patch,
    ProposedFix,
    SourceLocation,
)
from app.graph.state import DesignQAState
from app.integrations.axe.types import AccessibilityReport
from app.integrations.imaging.types import ComparisonResult, ImageDimensions
from app.integrations.llm.types import VisualReviewResult

CORPUS = {
    "index.html": [
        "<!DOCTYPE html>",
        "<html>",
        "  <head>",
        "    <title>Page</title>",
        "  </head>",
    ]
}


def _located(no_match: bool = False) -> FindingLocation:
    return FindingLocation(
        finding_title="html-has-lang",
        no_match=no_match,
        location=None
        if no_match
        else SourceLocation(
            file_path="index.html", line_start=2, line_end=2, code_evidence="<html>"
        ),
        explanation="The html element has no lang attribute.",
        confidence="high",
    )


def _fix(*, original_code: str, file_path: str = "index.html", no_fix: bool = False) -> ProposedFix:
    return ProposedFix(
        finding_title="html-has-lang",
        no_fix=no_fix,
        patch=None
        if no_fix
        else Patch(
            file_path=file_path,
            line_start=2,
            line_end=2,
            original_code=original_code,
            replacement_code='<html lang="en">',
        ),
        explanation="Adds the missing lang attribute.",
        confidence=FixConfidence.HIGH,
    )


def _state(*, code_analysis: CodeAnalysisResult | None, source_root: Path | None = Path("/tmp/x")):
    state = DesignQAState(
        project_id=uuid4(),
        figma_node={"name": "Hero"},
        figma_screenshot=b"png",
        target_url="https://example.com",
        source_root=source_root,
    )
    state.design_analysis = DesignAnalysisResult(layout_summary="l", design_intent="d")
    state.production_screenshot = b"png"
    state.comparison_result = ComparisonResult(
        expected_dimensions=ImageDimensions(width=1, height=1),
        actual_dimensions=ImageDimensions(width=1, height=1),
        dimensions_match=True,
        compared_dimensions=ImageDimensions(width=1, height=1),
        mismatched_pixels=0,
        total_pixels=1,
        mismatch_percentage=0.0,
    )
    state.diff_screenshot = b"png"
    state.visual_comparison = VisualReviewResult(material_drift_detected=True, summary="s")
    state.accessibility_report = AccessibilityReport(violations=[], violation_count=0)
    state.accessibility_interpretation = AccessibilityInterpretation(summary="s")
    state.aggregated_findings = AggregatedFindings(
        problems_found=True,
        findings=[
            AggregatedFinding(
                source=FindingSource.ACCESSIBILITY,
                priority=FindingPriority.HIGH,
                original_severity="high",
                title="html-has-lang",
                detail="Screen readers can't pick a language.",
            )
        ],
    )
    state.code_analysis = code_analysis
    return state


# --- verification -------------------------------------------------------


def test_accepts_a_patch_whose_original_code_is_really_in_the_file() -> None:
    verified = _verify(_fix(original_code="<html>"), CORPUS)

    assert verified.original_code_found is True


def test_flags_a_patch_against_code_that_does_not_exist() -> None:
    # The whole point of checking: a fluent, plausible patch aimed at code
    # the model reconstructed rather than read.
    verified = _verify(_fix(original_code='<html class="no-js">'), CORPUS)

    assert verified.original_code_found is False


def test_flags_a_patch_against_a_file_that_does_not_exist() -> None:
    verified = _verify(_fix(original_code="<html>", file_path="src/App.tsx"), CORPUS)

    assert verified.original_code_found is False


def test_tolerates_indentation_differences() -> None:
    # The model copies from a line-numbered snippet, so leading whitespace
    # is easy to lose. That doesn't change which code is being replaced.
    verified = _verify(_fix(original_code="        <head>"), CORPUS)

    assert verified.original_code_found is True


def test_matches_across_multiple_lines() -> None:
    verified = _verify(_fix(original_code="<html>\n  <head>"), CORPUS)

    assert verified.original_code_found is True


def test_empty_original_code_never_counts_as_found() -> None:
    # "" is in every string; treating that as a match would make the check
    # worthless exactly when the model returned nothing useful.
    verified = _verify(_fix(original_code="   \n  "), CORPUS)

    assert verified.original_code_found is False


def test_a_no_fix_proposal_is_not_marked_found() -> None:
    verified = _verify(_fix(original_code="", no_fix=True), CORPUS)

    assert verified.no_fix is True
    assert verified.original_code_found is False


# --- routing ------------------------------------------------------------


def test_routes_to_fix_once_something_is_located() -> None:
    state = _state(code_analysis=CodeAnalysisResult(summary="s", locations=[_located()]))

    assert route_after_supervisor(state) == NODE_FIX


def test_skips_fix_when_every_finding_was_a_no_match() -> None:
    # Nothing located means no file and no line range — a patch would have
    # to be invented rather than derived.
    state = _state(
        code_analysis=CodeAnalysisResult(summary="s", locations=[_located(no_match=True)])
    )

    assert route_after_supervisor(state) == NODE_END


def test_skips_fix_when_code_analysis_never_ran() -> None:
    state = _state(code_analysis=None, source_root=None)

    assert route_after_supervisor(state) == NODE_END


def test_ends_once_a_proposal_exists() -> None:
    state = _state(code_analysis=CodeAnalysisResult(summary="s", locations=[_located()]))
    state.fix_proposal = FixResult(summary="done", fixes=[])

    assert route_after_supervisor(state) == NODE_END


# --- prompt context -----------------------------------------------------


def test_prompt_carries_the_real_code_with_line_numbers() -> None:
    text = _build_context_text(
        [_located()],
        {"html-has-lang": _state(code_analysis=None).aggregated_findings.findings[0]},
        CORPUS,
    )

    assert "index.html lines 2-2" in text
    assert "2: <html>" in text
    # The finding's own wording, so the model knows what it's fixing.
    assert "Screen readers can't pick a language." in text


def test_prompt_says_so_when_there_is_nothing_to_patch() -> None:
    assert "nothing to patch" in _build_context_text([], {}, CORPUS)


@pytest.mark.parametrize("missing_path", ["gone.html"])
def test_prompt_handles_a_file_missing_from_the_checkout(missing_path: str) -> None:
    location = _located()
    assert location.location is not None
    location.location.file_path = missing_path

    text = _build_context_text([location], {}, CORPUS)

    assert "file not found" in text
