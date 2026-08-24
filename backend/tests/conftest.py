import functools
import http.server
import json
import threading
from pathlib import Path

import pytest
import respx
from httpx import Response

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


# Each graph node's system prompt opens distinctively, so a mocked
# Anthropic endpoint can answer based on *which agent is asking*.
#
# Positional mocking (`side_effect=[a, b, c]`) is not safe for this graph:
# the Accessibility Agent skips its LLM call entirely when axe-core finds
# no violations, which silently shifts every later response by one — the
# Code Analysis node then parses the accessibility payload, and because
# unrelated fields default rather than error, the test fails somewhere far
# from the cause.
AGENT_PROMPT_MARKERS = {
    "design_analysis": "preparing for a production-fidelity design QA pass",
    "visual_comparison": "You review a web page's visual implementation",
    "accessibility": "You triage a web page's accessibility violations",
    "code_analysis": "You locate the exact source code responsible",
}


def anthropic_response(parsed_json: dict) -> dict:
    """One Messages API response whose text content is `parsed_json`."""
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5",
        "content": [{"type": "text", "text": json.dumps(parsed_json)}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


def mock_anthropic_by_agent(responses: dict[str, dict]):
    """Mock /v1/messages, dispatching on the calling agent.

    `responses` maps an AGENT_PROMPT_MARKERS key to that agent's parsed
    payload. An agent that calls without a configured response fails the
    test loudly rather than silently receiving another agent's answer.
    """
    import json

    def respond(request) -> Response:
        system = json.loads(request.content)["system"]
        system_text = system if isinstance(system, str) else json.dumps(system)
        for agent, marker in AGENT_PROMPT_MARKERS.items():
            if marker in system_text and agent in responses:
                return Response(200, json=anthropic_response(responses[agent]))
        raise AssertionError(f"no mocked response for this agent prompt: {system_text[:160]}")

    return respx.post("https://api.anthropic.com/v1/messages").mock(side_effect=respond)
