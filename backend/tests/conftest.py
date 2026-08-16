import pytest

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
