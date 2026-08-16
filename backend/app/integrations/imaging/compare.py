"""Deterministic pixel-diff comparison between two PNGs.

No LLM/visual reasoning here — this is pure image processing (per
docs/principles.md #2). See ComparisonResult for what "deterministic"
means it does and doesn't tell you.
"""

from io import BytesIO

from PIL import Image
from pixelmatch.contrib.PIL import pixelmatch

from app.integrations.imaging.types import ComparisonResult, ImageDimensions

_TRANSPARENT = (255, 255, 255, 0)


def compare_images(
    expected_png: bytes, actual_png: bytes, *, threshold: float = 0.1
) -> tuple[ComparisonResult, bytes]:
    """Diff `expected_png` (Figma render) against `actual_png` (production).

    pixelmatch requires equal-sized inputs. If the two images differ in
    size, neither is stretched to fit the other — a size mismatch is
    itself a layout-drift signal we want to preserve, not hide (a 400x200
    Figma component rendered as 500x200 in production *is* the bug).
    Instead, both are padded (transparent, top-left anchored — matching
    how Figma's absoluteBoundingBox and DOM layout are both anchored) onto
    a shared canvas sized to the larger width/height of the two, so the
    extra/missing region shows up as real diff pixels rather than being
    silently discarded or distorted.

    Returns the structured result plus the diff visualization as PNG bytes.
    """
    expected_image = Image.open(BytesIO(expected_png)).convert("RGBA")
    actual_image = Image.open(BytesIO(actual_png)).convert("RGBA")

    expected_dimensions = ImageDimensions(width=expected_image.width, height=expected_image.height)
    actual_dimensions = ImageDimensions(width=actual_image.width, height=actual_image.height)
    dimensions_match = expected_dimensions == actual_dimensions

    canvas_size = (
        max(expected_image.width, actual_image.width),
        max(expected_image.height, actual_image.height),
    )
    expected_canvas = _pad_to_canvas(expected_image, canvas_size)
    actual_canvas = _pad_to_canvas(actual_image, canvas_size)

    diff_image = Image.new("RGBA", canvas_size)
    mismatched_pixels = pixelmatch(expected_canvas, actual_canvas, diff_image, threshold=threshold)

    total_pixels = canvas_size[0] * canvas_size[1]
    mismatch_percentage = (mismatched_pixels / total_pixels * 100) if total_pixels else 0.0

    result = ComparisonResult(
        expected_dimensions=expected_dimensions,
        actual_dimensions=actual_dimensions,
        dimensions_match=dimensions_match,
        compared_dimensions=ImageDimensions(width=canvas_size[0], height=canvas_size[1]),
        mismatched_pixels=mismatched_pixels,
        total_pixels=total_pixels,
        mismatch_percentage=round(mismatch_percentage, 4),
    )

    buffer = BytesIO()
    diff_image.save(buffer, format="PNG")
    return result, buffer.getvalue()


def _pad_to_canvas(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    if image.size == size:
        return image
    canvas = Image.new("RGBA", size, _TRANSPARENT)
    canvas.paste(image, (0, 0))
    return canvas
