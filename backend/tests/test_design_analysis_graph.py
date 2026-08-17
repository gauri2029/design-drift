"""Unit tests for the Design Analysis LangGraph workflow — the routing
logic in isolation (no LLM call), plus one full run through the compiled
graph with the Anthropic HTTP layer mocked (same approach as
test_llm_client.py: mock the HTTP layer, not the SDK, so the graph's own
wiring is actually exercised).
"""

import json
from uuid import uuid4

import pytest
import respx
from httpx import Response

from app.agents.supervisor import (
    NODE_DESIGN_ANALYSIS,
    NODE_END,
    route_after_supervisor,
    supervisor_node,
)
from app.agents.types import DesignAnalysisResult
from app.core.config import get_settings
from app.graph.state import DesignAnalysisState
from app.graph.workflow import run_design_analysis
from app.integrations.llm.exceptions import LLMNotConfiguredError

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


def _state(*, figma_node: dict | None = FIGMA_NODE) -> DesignAnalysisState:
    return DesignAnalysisState(
        project_id=uuid4(),
        figma_node=figma_node if figma_node is not None else {},
        figma_screenshot=b"fake-png-bytes",
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


def test_route_after_supervisor_goes_to_design_analysis_by_default() -> None:
    assert route_after_supervisor(_state()) == NODE_DESIGN_ANALYSIS


def test_route_after_supervisor_ends_once_error_is_set() -> None:
    state = _state()
    state.error = "no figma data"

    assert route_after_supervisor(state) == NODE_END


def test_route_after_supervisor_ends_once_result_is_set() -> None:
    state = _state()
    state.result = DesignAnalysisResult.model_validate(ANALYSIS_RESULT)

    assert route_after_supervisor(state) == NODE_END


@respx.mock
async def test_run_design_analysis_returns_the_llm_result(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, json=_anthropic_response(ANALYSIS_RESULT))
    )

    final_state = await run_design_analysis(_state())

    assert final_state.error is None
    assert final_state.result == DesignAnalysisResult.model_validate(ANALYSIS_RESULT)

    # The image and Figma metadata actually reached the model.
    request_body = json.loads(route.calls.last.request.content)
    content_blocks = request_body["messages"][0]["content"]
    assert content_blocks[0]["type"] == "image"
    assert "Hero" in content_blocks[-1]["text"]


@respx.mock
async def test_run_design_analysis_stops_at_supervisor_without_calling_the_llm(
    monkeypatch,
) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, json=_anthropic_response(ANALYSIS_RESULT))
    )

    final_state = await run_design_analysis(_state(figma_node={}))

    assert final_state.result is None
    assert final_state.error is not None
    assert route.call_count == 0


@respx.mock
async def test_run_design_analysis_propagates_llm_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")

    with pytest.raises(LLMNotConfiguredError):
        await run_design_analysis(_state())
