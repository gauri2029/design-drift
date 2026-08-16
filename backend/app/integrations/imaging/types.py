from pydantic import BaseModel


class ImageDimensions(BaseModel):
    width: int
    height: int


class ComparisonResult(BaseModel):
    """Raw, deterministic pixel-diff output — NOT a design fidelity score.

    This is `pixelmatch`'s mismatched-pixel percentage between two images,
    computed after normalizing them onto a shared canvas (padding, never
    stretching — see compare_images). It intentionally carries no notion of
    severity, category, or "what's actually wrong": that requires visual
    *reasoning*, which belongs to a later phase's LLM-backed comparison
    step, not this deterministic one (docs/principles.md #2).
    """

    expected_dimensions: ImageDimensions
    actual_dimensions: ImageDimensions
    dimensions_match: bool
    # The shared canvas size the diff actually ran on — max(width, height)
    # of the two inputs, since neither is scaled to match the other.
    compared_dimensions: ImageDimensions
    mismatched_pixels: int
    total_pixels: int
    mismatch_percentage: float
