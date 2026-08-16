import app.integrations.figma.cache as cache_module
from app.integrations.figma.cache import InMemoryTTLCache


def test_get_returns_none_for_missing_key() -> None:
    cache = InMemoryTTLCache()
    assert cache.get("missing") is None


def test_get_returns_the_value_before_ttl_expires(monkeypatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: now[0])

    cache = InMemoryTTLCache()
    cache.set("key", "value", ttl_seconds=10)

    now[0] += 5  # still within the TTL window
    assert cache.get("key") == "value"


def test_get_returns_none_after_ttl_expires(monkeypatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: now[0])

    cache = InMemoryTTLCache()
    cache.set("key", "value", ttl_seconds=10)

    now[0] += 11  # past the TTL window
    assert cache.get("key") is None


def test_expired_entry_is_evicted_on_get(monkeypatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: now[0])

    cache = InMemoryTTLCache()
    cache.set("key", "value", ttl_seconds=10)

    now[0] += 11
    cache.get("key")  # triggers eviction

    assert "key" not in cache._entries  # verifying internal cleanup, not just the public get()
