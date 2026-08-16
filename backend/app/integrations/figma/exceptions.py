class FigmaAPIError(Exception):
    """Raised when the Figma API returns an error or an unexpected response."""


class FigmaNodeNotFoundError(FigmaAPIError):
    """Raised when the requested node id is absent from the Figma response."""


class FigmaRateLimitError(FigmaAPIError):
    """Raised when Figma responds with 429 Too Many Requests.

    `retry_after_seconds` is populated when Figma's `Retry-After` header is
    present and parses as a plain integer/float. Figma may also send an
    HTTP-date instead (per the HTTP spec) — parsing that isn't worth the
    complexity for a dev-only cache, so it's left as None in that case.
    This is surfaced for callers that want it; no automatic retry is
    implemented here.
    """

    def __init__(self, retry_after_seconds: float | None = None) -> None:
        self.retry_after_seconds = retry_after_seconds
        message = "Figma rate limit reached. Please retry shortly."
        if retry_after_seconds is not None:
            message += f" (retry after {retry_after_seconds:.0f}s)"
        super().__init__(message)
