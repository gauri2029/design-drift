"""Compare two URLs for "is this the same page?".

Verification's before/after only means something when both captures came
from the same page. A before taken from a deployed site and an after taken
from a local dev server measure the difference between two *versions of the
site*, which then gets reported as damage a patch did — the worst failure
mode this tool has, because it's confidently wrong rather than merely
unhelpful.

That comparison is exact string work, so it's done here rather than asked
of a model (docs/principles.md #2). No LLM, no network, no DNS: this only
parses.
"""

from urllib.parse import urlsplit

# A dev server standing in for a deployed site is the *intended* use of
# verification's URL override, so localhost is not treated as a different
# page — that's the one substitution the feature exists to allow. Anything
# else differing is a real change of target.
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "[::1]", "::1", "0.0.0.0"})


def is_local(url: str) -> bool:
    return urlsplit(url).hostname in _LOCAL_HOSTS


def same_page(before: str, after: str) -> bool:
    """Whether two URLs address the same page for comparison purposes.

    Two cases, because they have different failure modes:

    - **Either side is local.** A dev server is the substitution this
      exists to permit, and it is trusted entirely: neither host nor path
      is compared. A deployment usually serves the site under a path prefix
      its dev server doesn't reproduce — GitHub Pages at
      `/workshops/2025-04-18-20y-cns/` is served by `python3 -m
      http.server` at `/` — so comparing paths here would reject the only
      case anyone uses the override for. The user is asserting "this local
      server is that site", and there is no way to check that from a URL;
      they can see both URLs in the result and judge it themselves.
    - **Neither side is local.** Both are deployed, so host and path are
      compared, and either differing is a different page. This is the case
      that produced wrong answers.

    Scheme and port are never compared, and neither are query and
    fragment — those route within a page, and treating them as different
    targets would block ordinary re-verifying.
    """
    before_parts, after_parts = urlsplit(before), urlsplit(after)

    # Trusted wholesale: see above. A local server's path bears no
    # necessary relation to the deployment's.
    if is_local(before) or is_local(after):
        return True

    return before_parts.hostname == after_parts.hostname and _normalize_path(
        before_parts.path
    ) == _normalize_path(after_parts.path)


def _normalize_path(path: str) -> str:
    stripped = path.rstrip("/")
    # "" and "/" are both the site root.
    return stripped or "/"
