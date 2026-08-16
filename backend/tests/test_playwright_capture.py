"""Playwright capture tests, against a local static fixture (no network)."""

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.integrations.playwright.capture import capture_screenshot
from app.integrations.playwright.exceptions import PlaywrightCaptureError

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "capture_fixture.html").as_uri()


async def test_full_page_screenshot_matches_document_size() -> None:
    png_bytes = await capture_screenshot(FIXTURE_URL, viewport_width=300, viewport_height=200)

    image = Image.open(BytesIO(png_bytes))
    assert image.size == (300, 200)


async def test_selector_screenshot_matches_element_bounds() -> None:
    png_bytes = await capture_screenshot(
        FIXTURE_URL, selector="#card", viewport_width=300, viewport_height=200
    )

    image = Image.open(BytesIO(png_bytes))
    assert image.size == (200, 100)
    # The element is a solid red box — spot-check a pixel away from any edge.
    assert image.convert("RGB").getpixel((100, 50)) == (255, 0, 0)


async def test_raises_when_selector_not_found() -> None:
    with pytest.raises(PlaywrightCaptureError, match="not found"):
        await capture_screenshot(FIXTURE_URL, selector="#does-not-exist")


async def test_raises_when_navigation_fails() -> None:
    with pytest.raises(PlaywrightCaptureError, match="failed to load"):
        await capture_screenshot("file:///no/such/fixture.html")
