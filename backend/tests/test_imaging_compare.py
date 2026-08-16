from io import BytesIO

from PIL import Image

from app.integrations.imaging.compare import compare_images


def _png_bytes(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_identical_images_have_zero_mismatch() -> None:
    image = _png_bytes((64, 32), (10, 20, 30))

    result, diff_png = compare_images(image, image)

    assert result.dimensions_match is True
    assert result.mismatched_pixels == 0
    assert result.mismatch_percentage == 0.0
    assert result.compared_dimensions.width == 64
    assert result.compared_dimensions.height == 32
    # diff output is still a valid, correctly-sized PNG
    assert Image.open(BytesIO(diff_png)).size == (64, 32)


def test_completely_different_solid_colors_mismatch_every_pixel() -> None:
    expected = _png_bytes((40, 20), (255, 0, 0))
    actual = _png_bytes((40, 20), (0, 255, 0))

    result, _ = compare_images(expected, actual)

    assert result.dimensions_match is True
    assert result.total_pixels == 40 * 20
    assert result.mismatched_pixels == 40 * 20
    assert result.mismatch_percentage == 100.0


def test_mismatched_dimensions_are_recorded_not_stretched() -> None:
    expected = _png_bytes((100, 50), (0, 0, 200))
    actual = _png_bytes((150, 50), (0, 0, 200))

    result, diff_png = compare_images(expected, actual)

    assert result.dimensions_match is False
    assert result.expected_dimensions.width == 100
    assert result.actual_dimensions.width == 150
    # Compared on the larger canvas, not a rescaled 100x50 or 150x50.
    assert result.compared_dimensions.width == 150
    assert result.compared_dimensions.height == 50
    assert Image.open(BytesIO(diff_png)).size == (150, 50)

    # The overlapping 100x50 region matches (same color); only the extra
    # 50x50 strip that exists in `actual` but not `expected` should differ.
    assert 0 < result.mismatched_pixels <= 50 * 50


def test_mismatched_dimensions_with_no_overlap_content_diff_is_full_extra_region() -> None:
    expected = _png_bytes((10, 10), (0, 0, 0))
    actual = _png_bytes((20, 10), (0, 0, 0))

    result, _ = compare_images(expected, actual)

    # Overlapping 10x10 region is identical; the extra 10x10 strip in
    # `actual` (opaque black) diffs against transparent padding (-> white).
    assert result.mismatched_pixels == 10 * 10
