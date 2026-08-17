"""Tests for app.integrations.llm.client's provider dispatch — the actual
new behavior added alongside gemini_client.py. Fakes out both provider
modules' generate_structured entirely (no HTTP involved): this is a test
of the routing decision itself, not either provider's request-building
(that's test_anthropic_client.py / test_gemini_client.py's job).
"""

from typing import Any

from pydantic import BaseModel

from app.core.config import get_settings
from app.integrations.llm import anthropic_client, client, gemini_client


class _Greeting(BaseModel):
    message: str


async def test_dispatches_to_anthropic_by_default(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", "anthropic")
    calls: list[str] = []

    async def fake_anthropic(**_kwargs: Any) -> _Greeting:
        calls.append("anthropic")
        return _Greeting(message="from anthropic")

    async def fake_gemini(**_kwargs: Any) -> _Greeting:
        calls.append("gemini")
        return _Greeting(message="from gemini")

    monkeypatch.setattr(anthropic_client, "generate_structured", fake_anthropic)
    monkeypatch.setattr(gemini_client, "generate_structured", fake_gemini)

    result = await client.generate_structured(
        system="s", text="t", images=[], output_format=_Greeting
    )

    assert calls == ["anthropic"]
    assert result == _Greeting(message="from anthropic")


async def test_dispatches_to_gemini_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", "gemini")
    calls: list[str] = []

    async def fake_anthropic(**_kwargs: Any) -> _Greeting:
        calls.append("anthropic")
        return _Greeting(message="from anthropic")

    async def fake_gemini(**_kwargs: Any) -> _Greeting:
        calls.append("gemini")
        return _Greeting(message="from gemini")

    monkeypatch.setattr(anthropic_client, "generate_structured", fake_anthropic)
    monkeypatch.setattr(gemini_client, "generate_structured", fake_gemini)

    result = await client.generate_structured(
        system="s", text="t", images=[], output_format=_Greeting
    )

    assert calls == ["gemini"]
    assert result == _Greeting(message="from gemini")
