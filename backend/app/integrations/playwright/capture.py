"""Deterministic browser capture of a live web page.

No LLM/judgment here — this only navigates and takes a screenshot (per
docs/principles.md #2). "Is this a good screenshot" is a later phase's
concern; this module just answers "what does the page look like."
"""

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.integrations.playwright.exceptions import PlaywrightCaptureError


async def capture_screenshot(
    url: str,
    *,
    selector: str | None = None,
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> bytes:
    """Screenshot `url`, optionally scoped to one element via `selector`.

    A fresh browser is launched per call rather than kept alive across
    requests — scans are infrequent/user-triggered, so the simplicity of
    not managing a shared browser's lifecycle outweighs the launch cost for
    now (revisit with an app-lifespan-scoped browser if scan volume ever
    makes that cost matter).

    `device_scale_factor=1` matches FigmaClient.get_image_url's scale=1
    default, so the two images compare_images() diffs are both CSS-pixel
    resolution rather than one being 2x/3x the other.
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height},
                device_scale_factor=1,
            )
            page = await context.new_page()

            try:
                await page.goto(url)
            except PlaywrightError as exc:
                raise PlaywrightCaptureError(f"failed to load {url!r}: {exc}") from exc

            if selector:
                locator = page.locator(selector)
                try:
                    await locator.wait_for(state="visible", timeout=10_000)
                except PlaywrightTimeoutError as exc:
                    raise PlaywrightCaptureError(
                        f"selector {selector!r} not found on {url!r}"
                    ) from exc
                return await locator.screenshot()

            return await page.screenshot(full_page=True)
        finally:
            await browser.close()
