class FigmaAPIError(Exception):
    """Raised when the Figma API returns an error or an unexpected response."""


class FigmaNodeNotFoundError(FigmaAPIError):
    """Raised when the requested node id is absent from the Figma response."""
