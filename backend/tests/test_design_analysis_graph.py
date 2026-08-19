"""Unit tests for the Design QA LangGraph workflow — the routing logic in
isolation (no LLM/browser call), plus one full run through the compiled
graph with the Anthropic HTTP layer and Playwright capture mocked (same
approach as test_anthropic_client.py: mock the HTTP layer, not the SDK, so
the graph's own wiring is actually exercised).
"""

import json
from io import BytesIO
from uuid import uuid4

import pytest
import respx
from httpx import Response
from PIL import Image

from app.agents.supervisor import (
    NODE_ACCESSIBILITY,
    NODE_AGGREGATE_FINDINGS,
    NODE_DESIGN_ANALYSIS,
    NODE_END,
    NODE_PRODUCTION_ANALYSIS,
    NODE_VISUAL_COMPARISON,
    route_after_supervisor,
    supervisor_node,
)
from app.agents.types import (
    AccessibilityInterpretation,
    AggregatedFindings,
    DesignAnalysisResult,
    FindingSource,
)
from app.core.config import get_settings
from app.graph.state import DesignQAState
from app.graph.workflow import run_design_qa
from app.integrations.axe.types import AccessibilityReport
from app.integrations.imaging.types import ComparisonResult, ImageDimensions
from app.integrations.llm.exceptions import LLMNotConfiguredError
from app.integrations.llm.types import VisualReviewResult
from app.integrations.playwright.exceptions import PlaywrightCaptureError

FIGMA_NODE = {
    "name": "Hero",
    "type": "FRAME",
    "layout_mode": "VERTICAL",
    "absolute_bounding_box": {"x": 0, "y": 0, "width": 1400, "height": 900},
}

ANALYSIS_RESULT = {
    "layout_summary": "A centered hero section with a heading, subtext, and one CTA button.",
    "design_intent": "Get the visitor to click the primary call-to-action.",
    "key_components": [
        {
            "name": "Primary CTA button",
            "role": "Drives the visitor to convert.",
            "notable_styling": "High-contrast fill, generous padding.",
        }
    ],
    "implementation_risks": ["The heading's exact vertical spacing may be easy to get wrong."],
}

VISUAL_COMPARISON_RESULT = {
    "material_drift_detected": True,
    "summary": "The button is visibly narrower in production than in Figma.",
    "findings": [
        {
            "category": "spacing",
            "severity": "major",
            "title": "Button is narrower than designed",
            "description": "Figma shows a wider button; production renders narrower.",
            "evidence": "The diff image highlights the button edge.",
            "likely_area": "the primary call-to-action button",
        }
    ],
}
ACCESSIBILITY_INTERPRETATION = {
    "summary": "One serious color-contrast violation affecting the primary CTA button.",
    "most_important_issues": [
        {
            "violation_id": "color-contrast",
            "user_impact": "Low-vision users may not be able to read the button's label.",
            "priority": "high",
        }
    ],
}
_SAMPLE_COMPARISON_RESULT = ComparisonResult(
    expected_dimensions=ImageDimensions(width=1400, height=900),
    actual_dimensions=ImageDimensions(width=1400, height=900),
    dimensions_match=True,
    compared_dimensions=ImageDimensions(width=1400, height=900),
    mismatched_pixels=0,
    total_pixels=1_260_000,
    mismatch_percentage=0.0,
)


def _png_bytes(size: tuple[int, int] = (10, 10)) -> bytes:
    image = Image.new("RGB", size, (255, 0, 0))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _state(*, figma_node: dict | None = FIGMA_NODE, target_url: str = "https://example.com"):
    return DesignQAState(
        project_id=uuid4(),
        figma_node=figma_node if figma_node is not None else {},
        figma_screenshot=_png_bytes(),
        target_url=target_url,
    )


def _anthropic_response(parsed_json: dict) -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5",
        "content": [{"type": "text", "text": json.dumps(parsed_json)}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


def test_supervisor_passes_through_when_figma_node_present() -> None:
    assert supervisor_node(_state()) == {}


def test_supervisor_sets_error_when_figma_node_missing() -> None:
    update = supervisor_node(_state(figma_node={}))

    assert update["error"] is not None
    assert "no recorded data" in update["error"]


def test_route_after_supervisor_goes_to_design_analysis_first() -> None:
    assert route_after_supervisor(_state()) == NODE_DESIGN_ANALYSIS


def test_route_after_supervisor_ends_once_error_is_set() -> None:
    state = _state()
    state.error = "no figma data"

    assert route_after_supervisor(state) == NODE_END


def test_route_after_supervisor_goes_to_production_analysis_after_design_analysis() -> None:
    state = _state()
    state.design_analysis = DesignAnalysisResult.model_validate(ANALYSIS_RESULT)

    assert route_after_supervisor(state) == NODE_PRODUCTION_ANALYSIS


def test_route_after_supervisor_goes_to_visual_comparison_after_production_analysis() -> None:
    state = _state()
    state.design_analysis = DesignAnalysisResult.model_validate(ANALYSIS_RESULT)
    state.production_screenshot = b"fake-production-png"

    assert route_after_supervisor(state) == NODE_VISUAL_COMPARISON


def test_route_after_supervisor_goes_to_accessibility_after_visual_comparison() -> None:
    state = _state()
    state.design_analysis = DesignAnalysisResult.model_validate(ANALYSIS_RESULT)
    state.production_screenshot = b"fake-production-png"
    state.comparison_result = _SAMPLE_COMPARISON_RESULT
    state.diff_screenshot = b"fake-diff-png"
    state.visual_comparison = VisualReviewResult.model_validate(VISUAL_COMPARISON_RESULT)

    assert route_after_supervisor(state) == NODE_ACCESSIBILITY


def _fully_analyzed_state() -> DesignQAState:
    """Everything up to (but not including) the findings aggregation."""
    state = _state()
    state.design_analysis = DesignAnalysisResult.model_validate(ANALYSIS_RESULT)
    state.production_screenshot = b"fake-production-png"
    state.comparison_result = _SAMPLE_COMPARISON_RESULT
    state.diff_screenshot = b"fake-diff-png"
    state.visual_comparison = VisualReviewResult.model_validate(VISUAL_COMPARISON_RESULT)
    state.accessibility_report = AccessibilityReport(violations=[], violation_count=0)
    state.accessibility_interpretation = AccessibilityInterpretation.model_validate(
        ACCESSIBILITY_INTERPRETATION
    )
    return state


def test_route_after_supervisor_goes_to_aggregation_after_accessibility() -> None:
    assert route_after_supervisor(_fully_analyzed_state()) == NODE_AGGREGATE_FINDINGS


def test_route_after_supervisor_ends_once_findings_are_aggregated() -> None:
    state = _fully_analyzed_state()
    state.aggregated_findings = AggregatedFindings(problems_found=False, findings=[])

    assert route_after_supervisor(state) == NODE_END


@respx.mock
async def test_run_design_qa_returns_every_nodes_output(monkeypatch, fixture_server) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    # design_analysis, visual_comparison, and (if capture_fixture.html has
    # any axe-core violations — it's missing <html lang>, so it should)
    # accessibility each make one LLM call, in that order. A 3rd entry is
    # harmless if accessibility ends up with zero violations and skips its
    # LLM call entirely (see app.agents.accessibility's docstring).
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        side_effect=[
            Response(200, json=_anthropic_response(ANALYSIS_RESULT)),
            Response(200, json=_anthropic_response(VISUAL_COMPARISON_RESULT)),
            Response(200, json=_anthropic_response(ACCESSIBILITY_INTERPRETATION)),
        ]
    )

    host, port = fixture_server.server_address[:2]
    final_state = await run_design_qa(
        _state(target_url=f"http://{host}:{port}/capture_fixture.html")
    )

    assert final_state.error is None
    assert final_state.design_analysis == DesignAnalysisResult.model_validate(ANALYSIS_RESULT)
    assert final_state.production_screenshot is not None
    assert final_state.production_screenshot.startswith(b"\x89PNG")
    # figma_screenshot is a small placeholder PNG, not sized to match the
    # captured page, so dimensions_match isn't asserted here — just that
    # image diffing actually ran and produced a real result/diff image.
    assert final_state.comparison_result is not None
    assert 0.0 <= final_state.comparison_result.mismatch_percentage <= 100.0
    assert final_state.diff_screenshot is not None
    assert final_state.diff_screenshot.startswith(b"\x89PNG")
    assert final_state.visual_comparison == VisualReviewResult.model_validate(
        VISUAL_COMPARISON_RESULT
    )
    assert final_state.accessibility_report is not None
    assert final_state.accessibility_interpretation is not None

    # The aggregation ran last and saw both agents' findings — the mocked
    # visual result reports one major finding, so it must appear, and
    # problems_found must be True.
    aggregated = final_state.aggregated_findings
    assert aggregated is not None
    assert aggregated.problems_found is True
    assert any(
        finding.source == FindingSource.VISUAL_COMPARISON
        and finding.title == VISUAL_COMPARISON_RESULT["findings"][0]["title"]
        for finding in aggregated.findings
    )

    # The Design Analysis call carried the Figma image and metadata...
    first_request = json.loads(route.calls[0].request.content)
    first_blocks = first_request["messages"][0]["content"]
    assert first_blocks[0]["type"] == "image"
    assert "Hero" in first_blocks[-1]["text"]

    # ...the Visual Comparison call carried all three images (Figma,
    # production, diff) plus the deterministic pixel-diff percentage...
    second_request = json.loads(route.calls[1].request.content)
    second_blocks = second_request["messages"][0]["content"]
    assert sum(1 for block in second_blocks if block["type"] == "image") == 3
    assert "pixel diff" in second_blocks[-1]["text"]

    # ...and if accessibility made a call at all, it was text-only (axe
    # violation data, not images).
    if route.call_count == 3:
        third_request = json.loads(route.calls[2].request.content)
        third_blocks = third_request["messages"][0]["content"]
        assert all(block["type"] == "text" for block in third_blocks)


@respx.mock
async def test_run_design_qa_stops_at_supervisor_without_calling_the_llm(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, json=_anthropic_response(ANALYSIS_RESULT))
    )

    final_state = await run_design_qa(_state(figma_node={}))

    assert final_state.design_analysis is None
    assert final_state.error is not None
    assert route.call_count == 0


@respx.mock
async def test_run_design_qa_propagates_llm_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")

    with pytest.raises(LLMNotConfiguredError):
        await run_design_qa(_state())


@respx.mock
async def test_run_design_qa_propagates_capture_error_after_design_analysis(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, json=_anthropic_response(ANALYSIS_RESULT))
    )

    # No fixture server for this target_url — the page load itself fails.
    with pytest.raises(PlaywrightCaptureError):
        await run_design_qa(_state(target_url="http://127.0.0.1:1/unreachable"))
