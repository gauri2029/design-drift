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

import asyncio
import logging
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.integrations.llm.exceptions import LLMNotConfiguredError, LLMResponseError

logger = logging.getLogger(__name__)

# Retries live here rather than in the caller because this is where the
# HTTP status is still visible. The Anthropic SDK retries transient
# failures itself (max_retries=2 by default); the Google SDK does not
# unless you pass http_options.retry_options — its default retry policy is
# tenacity's stop_after_attempt(1), i.e. no retry at all. We don't pass
# that option, so the loop below is the only one and nothing is multiplied.
#
# Statuses that say "try again", not "your request is wrong": 429 is the
# free tier's rate limit, 500/503 are Gemini being busy or briefly broken.
# Everything else — a bad key, a malformed schema, an unknown model — fails
# on the first attempt, because retrying it would just be slower.
_RETRYABLE_STATUS = frozenset({429, 500, 503})

# Three attempts per model over ~4.5s, two models, so the worst case is
# ~9s of waiting before the whole call gives up. A workflow run has already
# paid for a browser capture and several model calls by the time it reaches
# here, so riding out a spike is far cheaper than discarding all of it —
# but a user is watching an SSE stream, so this cannot spend minutes.
_MAX_ATTEMPTS = 3
_FIRST_DELAY_SECONDS = 1.5

# Tried only after the configured model has exhausted its own attempts.
# A sustained 503 usually means one model is oversubscribed rather than the
# whole API being down, so a second free-tier model is a real second chance
# rather than a retry in disguise.
_FALLBACK_MODEL = "gemini-3.8-flash"


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
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_json_schema=output_format.model_json_schema(),
    )

    # Primary first, fallback only once the primary is exhausted. Skipped
    # entirely when they are the same name, or the "fallback" would just be
    # three more attempts at the model that was already unavailable.
    models = [settings.gemini_model]
    if _FALLBACK_MODEL != settings.gemini_model:
        models.append(_FALLBACK_MODEL)

    response = None
    for index, model in enumerate(models):
        is_fallback = index > 0
        if is_fallback:
            logger.warning(
                "Gemini model %s is unavailable, falling back to %s", models[0], model
            )
        try:
            response = await _call_with_retry(
                client=client, model=model, contents=contents, config=config
            )
        except APIError as exc:
            # A permanent error, or the last model in the chain: either way
            # there is nothing left to try.
            if exc.code not in _RETRYABLE_STATUS or is_fallback:
                raise LLMResponseError(_failure_message(models, exc, is_fallback)) from exc
            continue
        if is_fallback:
            logger.info("Gemini fallback model %s succeeded", model)
        break

    # Defensive: the loop above either assigns a response, raises, or
    # continues to another model, so this cannot be reached.
    if response is None:  # pragma: no cover
        raise AssertionError("unreachable")

    if not response.text:
        raise LLMResponseError("model response had no text content")
    try:
        return output_format.model_validate_json(response.text)
    except ValidationError as exc:
        raise LLMResponseError(
            f"model response did not match the expected schema: {exc}"
        ) from exc


async def _call_with_retry(
    *,
    client: genai.Client,
    model: str,
    contents: list[Any],
    config: types.GenerateContentConfig,
) -> types.GenerateContentResponse:
    """One model, up to `_MAX_ATTEMPTS` times, with exponential backoff.

    Raises the underlying APIError rather than wrapping it, so the caller
    can tell a transient exhaustion (worth trying another model) from a
    permanent one (worth giving up on immediately).
    """
    delay = _FIRST_DELAY_SECONDS
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            logger.info("Calling Gemini model %s (attempt %d of %d)", model, attempt, _MAX_ATTEMPTS)
            return await client.aio.models.generate_content(
                model=model, contents=contents, config=config
            )
        except APIError as exc:
            if exc.code not in _RETRYABLE_STATUS or attempt == _MAX_ATTEMPTS:
                raise
            logger.warning(
                "Gemini model %s returned %s, retrying in %.1fs (attempt %d of %d)",
                model,
                exc.code,
                delay,
                attempt,
                _MAX_ATTEMPTS,
            )
            await asyncio.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")  # pragma: no cover


def _failure_message(models: list[str], exc: APIError, exhausted_fallback: bool) -> str:
    """Say which models were tried, so a 503 doesn't read as a code bug."""
    if exhausted_fallback:
        return (
            f"Gemini request failed: both the primary model ({models[0]}) and the "
            f"fallback ({models[-1]}) were unavailable after {_MAX_ATTEMPTS} attempts "
            f"each. Last error: {exc}"
        )
    return f"Gemini request failed: {exc}"
