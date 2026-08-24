"""Tests for the Claude structured-output wrapper.

Mocks the raw Anthropic Messages API response via respx — no real API key
or network call. This is deliberately not a mock of the anthropic SDK
itself: we mock the HTTP layer it sits on (as with FigmaClient's tests),
so we're actually exercising the SDK's request-building and
response-parsing code, not assuming it works.
"""

import json

import pytest
import respx
from httpx import Response
from pydantic import BaseModel

from app.core.config import get_settings
from app.integrations.llm.anthropic_client import generate_structured
from app.integrations.llm.exceptions import LLMNotConfiguredError, LLMResponseError


class _Greeting(BaseModel):
    message: str


def _anthropic_response(parsed_json: dict) -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5",
        "content": [{"type": "text", "text": json.dumps(parsed_json)}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


@respx.mock
async def test_generate_structured_returns_validated_model(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, json=_anthropic_response({"message": "hello"}))
    )

    result = await generate_structured(
        system="You are terse.",
        text="Say hello.",
        images=[b"fake-png-bytes"],
        output_format=_Greeting,
    )

    assert result == _Greeting(message="hello")

    # Confirm the request actually carries the image and the derived schema —
    # not just that *some* request landed.
    request_body = json.loads(route.calls.last.request.content)
    content_blocks = request_body["messages"][0]["content"]
    assert content_blocks[0]["type"] == "image"
    assert content_blocks[0]["source"]["media_type"] == "image/png"
    assert content_blocks[-1] == {"type": "text", "text": "Say hello."}
    assert request_body["system"] == "You are terse."
    assert request_body["output_config"]["format"]["type"] == "json_schema"
    assert request_body["model"] == "claude-opus-5"


@respx.mock
async def test_generate_structured_raises_when_key_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")

    with pytest.raises(LLMNotConfiguredError):
        await generate_structured(system="s", text="t", images=[], output_format=_Greeting)


@respx.mock
async def test_generate_structured_raises_when_response_is_not_valid_json(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-5",
                "content": [{"type": "text", "text": "not json"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )
    )

    with pytest.raises(LLMResponseError):
        await generate_structured(system="s", text="t", images=[], output_format=_Greeting)
