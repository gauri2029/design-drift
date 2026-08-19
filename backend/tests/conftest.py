import functools
import http.server
import threading
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.integrations.figma.cache import get_figma_cache

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def fixture_server():
    """A local HTTP server over tests/fixtures/ — the "production app" for
    tests that need Playwright to actually load a page (test_scans_api.py,
    test_design_analysis_*.py). Real local server, not a file:// URL or an
    external site — deterministic and keeps target_url http(s), which
    ProjectCreate requires.
    """
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(FIXTURES_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    thread.join()


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
