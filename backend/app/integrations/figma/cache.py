"""Minimal in-memory TTL cache for Figma API responses.

Purpose: repeated local testing/development re-registers the same
project (same file_key/node_id) over and over, and Figma's personal
access tokens have a low rate limit — this avoids re-hitting Figma's API
for data that hasn't changed in the last few minutes.

Deliberately simple: no Redis, no persistence, no background eviction, no
invalidation beyond "expired." A process restart clears it, which is fine
for its purpose (docs/principles.md #1/#6 — add complexity only when a
concrete need appears). Kept behind a small Protocol so the in-memory
implementation can be swapped later (e.g. a shared cache across worker
processes) without touching callers.
"""

import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol


class TTLCache(Protocol):
    def get(self, key: str) -> object | None: ...
    def set(self, key: str, value: object, ttl_seconds: float) -> None: ...


@dataclass
class _Entry:
    value: object
    expires_at: float


class InMemoryTTLCache:
    """Process-local TTL cache backed by a plain dict.

    Entries are only checked for expiry lazily, on `get()` — there's no
    background sweep. For a dev-scale cache (a handful of projects, a
    10-minute TTL) that's the right tradeoff: a background sweeper would
    be complexity with no real benefit here.
    """

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}

    def get(self, key: str) -> object | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at < time.monotonic():
            del self._entries[key]
            return None
        return entry.value

    def set(self, key: str, value: object, ttl_seconds: float) -> None:
        self._entries[key] = _Entry(value=value, expires_at=time.monotonic() + ttl_seconds)


@lru_cache
def get_figma_cache() -> InMemoryTTLCache:
    """Process-wide singleton, so repeated FigmaClient instances (one is
    created per request — see app.services.projects) actually share a
    cache instead of each starting empty.
    """
    return InMemoryTTLCache()
