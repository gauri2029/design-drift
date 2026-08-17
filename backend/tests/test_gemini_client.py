"""Tests for the Gemini structured-output wrapper — the Gemini counterpart
to test_anthropic_client.py.

Mocks the raw generativelanguage.googleapis.com response via respx — no
real API key or network call. As with test_anthropic_client.py, this
mocks the HTTP layer the SDK sits on, not the SDK itself.
"""

import json

import pytest
import respx
from google.genai.errors import APIError, ClientError
from httpx import Response
from pydantic import BaseModel

from app.core.config import get_settings
from app.integrations.llm.exceptions import LLMNotConfiguredError, LLMResponseError
from app.integrations.llm.gemini_client import generate_structured

GENERATE_CONTENT_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
)


class _Greeting(BaseModel):
    message: str


def _gemini_response(parsed_json: dict) -> dict:
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": json.dumps(parsed_json)}], "role": "model"},
                "finishReason": "STOP",
            }
        ],
    }


@respx.mock
async def test_generate_structured_returns_validated_model(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    route = respx.post(GENERATE_CONTENT_URL).mock(
        return_value=Response(200, json=_gemini_response({"message": "hello"}))
    )

    result = await generate_structured(
        system="You are terse.",
        text="Say hello.",
        images=[b"fake-png-bytes"],
        output_format=_Greeting,
    )

    assert result == _Greeting(message="hello")

    # Confirm the request actually carries the image and the derived schema.
    request_body = json.loads(route.calls.last.request.content)
    parts = request_body["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mimeType"] == "image/png"
    assert parts[-1] == {"text": "Say hello."}
    assert request_body["systemInstruction"]["parts"][0]["text"] == "You are terse."
    assert request_body["generationConfig"]["responseJsonSchema"] == _Greeting.model_json_schema()


@respx.mock
async def test_generate_structured_raises_when_key_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")

    with pytest.raises(LLMNotConfiguredError):
        await generate_structured(system="s", text="t", images=[], output_format=_Greeting)


@respx.mock
async def test_generate_structured_raises_when_response_is_not_valid_json(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    respx.post(GENERATE_CONTENT_URL).mock(
        return_value=Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "not json"}], "role": "model"}},
                ],
            },
        )
    )

    with pytest.raises(LLMResponseError):
        await generate_structured(system="s", text="t", images=[], output_format=_Greeting)


@respx.mock
async def test_generate_structured_raises_when_gemini_returns_an_error(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    respx.post(GENERATE_CONTENT_URL).mock(
        return_value=Response(
            429,
            json={
                "error": {"code": 429, "message": "rate limited", "status": "RESOURCE_EXHAUSTED"}
            },
        )
    )

    with pytest.raises(LLMResponseError):
        await generate_structured(system="s", text="t", images=[], output_format=_Greeting)


def test_client_error_is_an_api_error() -> None:
    # Sanity check on the assumption gemini_client.py relies on: ClientError
    # (4xx) is caught by the broader `except APIError` it actually uses.
    assert issubclass(ClientError, APIError)
