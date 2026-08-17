"""Thin wrapper around Claude's multimodal structured-output call — the
Anthropic-backed implementation behind app.integrations.llm.client's
provider dispatch (see that module's docstring for why there are two of
these instead of a provider abstraction).

Deliberately thin, not a generic "call_llm()" abstraction: the system
prompt, the multimodal content blocks, and the actual SDK call are all
visible here rather than hidden behind a framework, since this project
exists partly to teach these concepts (docs/principles.md #3).

Uses `client.messages.parse()` — the Anthropic SDK's structured-output
helper. It derives a JSON schema from `output_format` (a Pydantic model),
sends it as `output_config.format`, and validates the model's response
against that schema client-side before returning it as `.parsed_output`.
"""

import base64

from anthropic import APIError, AsyncAnthropic
from anthropic.types import ImageBlockParam, MessageParam, TextBlockParam
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.integrations.llm.exceptions import LLMNotConfiguredError, LLMResponseError


def _image_content_block(png_bytes: bytes) -> ImageBlockParam:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.standard_b64encode(png_bytes).decode("ascii"),
        },
    }


async def generate_structured[ResultT: BaseModel](
    *,
    system: str,
    text: str,
    images: list[bytes],
    output_format: type[ResultT],
) -> ResultT:
    """Make one multimodal call to Claude, validated against `output_format`.

    Content blocks are ordered images-then-text, per Anthropic's vision
    guidance (an image referenced by later text should precede it).
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise LLMNotConfiguredError("ANTHROPIC_API_KEY is not configured")

    content: list[ImageBlockParam | TextBlockParam] = [
        _image_content_block(png) for png in images
    ]
    content.append({"type": "text", "text": text})
    messages: list[MessageParam] = [{"role": "user", "content": content}]

    async with AsyncAnthropic(api_key=settings.anthropic_api_key) as client:
        try:
            response = await client.messages.parse(
                model=settings.anthropic_model,
                max_tokens=4096,
                system=system,
                messages=messages,
                output_format=output_format,
            )
        except (APIError, ValidationError) as exc:
            raise LLMResponseError(f"Claude request failed: {exc}") from exc

    if response.parsed_output is None:
        raise LLMResponseError("model response did not match the expected schema")
    return response.parsed_output
