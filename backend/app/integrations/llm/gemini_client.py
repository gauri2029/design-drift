"""Thin wrapper around Gemini's multimodal structured-output call — the
Gemini-backed implementation behind app.integrations.llm.client's provider
dispatch (see that module's docstring). Mirrors anthropic_client.py's
shape and signature deliberately, so both are equally easy to read end to
end (docs/principles.md #3) rather than hidden behind a shared interface.

Uses `client.aio.models.generate_content()` with `response_json_schema`
set from `output_format.model_json_schema()`. Unlike the Anthropic SDK's
`.parsed_output`, this SDK doesn't validate/parse the response back into
the Pydantic model itself — it just constrains the model's JSON output to
match the schema — so `output_format.model_validate_json()` is called
explicitly here.
"""

from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.integrations.llm.exceptions import LLMNotConfiguredError, LLMResponseError


async def generate_structured[ResultT: BaseModel](
    *,
    system: str,
    text: str,
    images: list[bytes],
    output_format: type[ResultT],
) -> ResultT:
    """Make one multimodal call to Gemini, validated against `output_format`.

    Content is ordered images-then-text, matching anthropic_client's
    ordering for consistency across providers (Gemini itself isn't strict
    about this the way Anthropic's vision guidance recommends).
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMNotConfiguredError("GEMINI_API_KEY is not configured")

    # list[Any]: the SDK's accepted-contents union is broad (str | Image |
    # File | Part | ...) and list is invariant, so a precise element type
    # here wouldn't structurally match generate_content's signature anyway.
    contents: list[Any] = [
        types.Part.from_bytes(data=png, mime_type="image/png") for png in images
    ]
    contents.append(text)

    client = genai.Client(api_key=settings.gemini_api_key)
    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_json_schema=output_format.model_json_schema(),
            ),
        )
    except APIError as exc:
        raise LLMResponseError(f"Gemini request failed: {exc}") from exc

    if not response.text:
        raise LLMResponseError("model response had no text content")
    try:
        return output_format.model_validate_json(response.text)
    except ValidationError as exc:
        raise LLMResponseError(
            f"model response did not match the expected schema: {exc}"
        ) from exc
