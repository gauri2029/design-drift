"""A small in-process rate limiter for the unauthenticated write surface.

Scope, honestly stated: this is a per-process, in-memory sliding window. It
stops a script from opening ten thousand accounts on the public deployment,
which is the actual exposure of putting a signup form on a public URL. It is
not a defence against a distributed attacker, and it resets on restart.
Redis would fix both and is the right answer at the point this runs on more
than one instance — until then it would be a service to operate for a
counter that fits in a dict (docs/principles.md #6).

Deliberately applied only to signup. Login is not limited here because
throttling it by IP lets an attacker lock a shared NAT out of their own
accounts; argon2's own cost is what makes password guessing expensive.
"""

import time
from collections import defaultdict, deque
from threading import Lock

_WINDOW_SECONDS = 3600

# IP -> timestamps of recent attempts, oldest first.
_attempts: dict[str, deque[float]] = defaultdict(deque)
# Uvicorn can serve requests from a thread pool, so the dict needs guarding.
_lock = Lock()


def reset() -> None:
    """Forget every recorded attempt. For tests."""
    with _lock:
        _attempts.clear()


def check(key: str, limit: int) -> bool:
    """Record an attempt by `key`, returning whether it is within `limit`.

    A limit of 0 or less disables the check, which is how a local checkout
    and the test suite avoid being throttled.

    Counts the attempt even when it fails: otherwise an over-limit caller
    would be let through as soon as the window slid, one request at a time,
    forever.
    """
    if limit <= 0:
        return True

    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS

    with _lock:
        seen = _attempts[key]
        while seen and seen[0] < cutoff:
            seen.popleft()

        # Bounded so a flood from one IP can't grow the deque without limit:
        # once over, there's nothing more to learn from recording another.
        if len(seen) >= limit:
            return False

        seen.append(now)
        return True
