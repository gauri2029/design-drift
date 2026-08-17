"""Picks which provider backs `generate_structured()` — the one function
every LLM call site in this codebase imports (app.services.reviews,
app.agents.design_analysis).

Two providers, not a formal Protocol/interface: anthropic_client.py and
gemini_client.py already share an identical signature and are each simple
enough to read end to end (docs/principles.md #3 — this project avoids
provider-abstraction machinery until there's a real reason for it, per
docs/principles.md #6). This module is the entire "abstraction" — a
five-line if/else keyed off `settings.llm_provider`, so callers don't need
to know or care which provider is configured.
"""

from pydantic import BaseModel

from app.core.config import get_settings
from app.integrations.llm import anthropic_client, gemini_client


async def generate_structured[ResultT: BaseModel](
    *,
    system: str,
    text: str,
    images: list[bytes],
    output_format: type[ResultT],
) -> ResultT:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        return await anthropic_client.generate_structured(
            system=system, text=text, images=images, output_format=output_format
        )
    return await gemini_client.generate_structured(
        system=system, text=text, images=images, output_format=output_format
    )
