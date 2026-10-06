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
from app.integrations.llm import gemini_client
from app.integrations.llm.exceptions import LLMNotConfiguredError, LLMResponseError
from app.integrations.llm.gemini_client import generate_structured


def _url(model: str) -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


# conftest pins gemini_model so these don't depend on local .env settings.
PRIMARY_MODEL = "gemini-2.5-flash"
GENERATE_CONTENT_URL = _url(PRIMARY_MODEL)
FALLBACK_URL = _url(gemini_client._FALLBACK_MODEL)

_BUSY = {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}}


def _busy() -> Response:
    return Response(503, json=_BUSY)


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


@pytest.fixture
def no_sleep(monkeypatch):
    """Run the retry loop without waiting, and record what it waited for.

    Patching the module's own `asyncio.sleep` keeps the delays out of the
    public signature — a `delay=0` parameter would exist only for tests —
    and lets a test assert the backoff actually doubles.
    """
    waited: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(gemini_client.asyncio, "sleep", fake_sleep)
    return waited


@respx.mock
async def test_primary_succeeding_immediately_makes_no_extra_calls(monkeypatch, no_sleep) -> None:
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    primary = respx.post(GENERATE_CONTENT_URL).mock(
        return_value=Response(200, json=_gemini_response({"message": "hello"}))
    )
    fallback = respx.post(FALLBACK_URL).mock(return_value=Response(200, json={}))

    result = await generate_structured(system="s", text="t", images=[], output_format=_Greeting)

    assert result == _Greeting(message="hello")
    assert primary.call_count == 1
    # The fallback costs a second model's quota, so it must stay untouched
    # on the happy path.
    assert not fallback.called
    assert no_sleep == []


@respx.mock
async def test_primary_recovers_after_one_transient_failure(monkeypatch, no_sleep) -> None:
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    # Gemini's own wording when a model is oversubscribed — it says nothing
    # about whether the request was valid, so the run shouldn't be lost.
    primary = respx.post(GENERATE_CONTENT_URL).mock(
        side_effect=[_busy(), Response(200, json=_gemini_response({"message": "hello"}))]
    )
    fallback = respx.post(FALLBACK_URL).mock(return_value=Response(200, json={}))

    result = await generate_structured(system="s", text="t", images=[], output_format=_Greeting)

    assert result == _Greeting(message="hello")
    assert primary.call_count == 2
    assert not fallback.called
    assert no_sleep == [1.5]


@respx.mock
async def test_fallback_runs_only_after_the_primary_is_exhausted(monkeypatch, no_sleep) -> None:
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    primary = respx.post(GENERATE_CONTENT_URL).mock(return_value=_busy())
    fallback = respx.post(FALLBACK_URL).mock(
        return_value=Response(200, json=_gemini_response({"message": "from fallback"}))
    )

    result = await generate_structured(system="s", text="t", images=[], output_format=_Greeting)

    assert result == _Greeting(message="from fallback")
    # Every primary attempt is spent before the second model is touched.
    assert primary.call_count == gemini_client._MAX_ATTEMPTS
    assert fallback.call_count == 1
    assert no_sleep == [1.5, 3.0]


@respx.mock
async def test_both_models_failing_says_so_explicitly(monkeypatch, no_sleep) -> None:
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    primary = respx.post(GENERATE_CONTENT_URL).mock(return_value=_busy())
    fallback = respx.post(FALLBACK_URL).mock(return_value=_busy())

    with pytest.raises(LLMResponseError) as excinfo:
        await generate_structured(system="s", text="t", images=[], output_format=_Greeting)

    # Naming both models is what stops a capacity problem reading as a bug
    # in Design Drift.
    message = str(excinfo.value)
    assert PRIMARY_MODEL in message
    assert gemini_client._FALLBACK_MODEL in message
    assert primary.call_count == gemini_client._MAX_ATTEMPTS
    assert fallback.call_count == gemini_client._MAX_ATTEMPTS
    # Bounded: a run that retried forever would hang the SSE stream.
    assert no_sleep == [1.5, 3.0, 1.5, 3.0]


@respx.mock
async def test_a_permanent_error_is_not_retried_and_skips_the_fallback(
    monkeypatch, no_sleep
) -> None:
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    primary = respx.post(GENERATE_CONTENT_URL).mock(
        return_value=Response(
            400,
            json={"error": {"code": 400, "message": "bad", "status": "INVALID_ARGUMENT"}},
        )
    )
    fallback = respx.post(FALLBACK_URL).mock(return_value=Response(200, json={}))

    with pytest.raises(LLMResponseError):
        await generate_structured(system="s", text="t", images=[], output_format=_Greeting)

    # A malformed request fails identically on every model, so retrying it
    # or switching models only delays the same error.
    assert primary.call_count == 1
    assert not fallback.called
    assert no_sleep == []


def test_client_error_is_an_api_error() -> None:
    # Sanity check on the assumption gemini_client.py relies on: ClientError
    # (4xx) is caught by the broader `except APIError` it actually uses.
    assert issubclass(ClientError, APIError)
