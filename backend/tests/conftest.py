import pytest

from app.core.config import get_settings
from app.integrations.figma.cache import get_figma_cache


@pytest.fixture(autouse=True)
def _reset_figma_cache():
    """FigmaClient defaults to the process-wide cache singleton (that's
    the point — see app.integrations.figma.cache's docstring), but several
    test files reuse the same file_key/node_id constants. Without this,
    whichever test happens to run first would populate the cache and every
    later test with the same key would silently get its cached response
    instead of hitting its own respx mock.
    """
    get_figma_cache.cache_clear()
    yield
    get_figma_cache.cache_clear()


@pytest.fixture(autouse=True)
def _pin_llm_provider_settings(monkeypatch):
    """Settings() reads the developer's real .env — without this, LLM tests
    would pass or fail depending on whatever LLM_PROVIDER/GEMINI_MODEL the
    developer happens to have configured locally (e.g. after switching to
    the Gemini free tier for their own dev use), rather than the code's own
    defaults the tests are actually written against. test_llm_provider_dispatch.py
    overrides these per-test anyway to exercise both branches.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "gemini_model", "gemini-2.5-flash")
