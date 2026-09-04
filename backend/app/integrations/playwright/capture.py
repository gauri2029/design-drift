"""Deterministic browser capture of a live web page.

No LLM/judgment here — this navigates, takes a screenshot, and reads the
DOM (per docs/principles.md #2). "Is this a good screenshot" is a later
phase's concern; this module just answers "what does the page look like"
and "what is it made of."
"""

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel

from app.integrations.playwright.dom import DomSnapshot, extract_dom_snapshot
from app.integrations.playwright.exceptions import PlaywrightCaptureError


class PageCapture(BaseModel):
    """A screenshot and the DOM behind it, from one page load.

    Together rather than as two calls because they have to describe the
    same render: capturing twice can catch a page in two different states,
    and then a finding drawn from the image would be located using
    evidence from a page nobody looked at.
    """

    screenshot: bytes
    dom: DomSnapshot


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

            return await _screenshot(page, url, selector)
        finally:
            await browser.close()


async def capture_page(
    url: str,
    *,
    selector: str | None = None,
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> PageCapture:
    """Screenshot `url` and snapshot its DOM in the same page load.

    Same browser/viewport rules as capture_screenshot — this is that
    function plus the DOM read, kept as a separate entry point so callers
    that only want pixels (scans, breakpoint captures) don't pay for the
    extra evaluate.

    The DOM snapshot always covers the whole page, even when `selector`
    scopes the screenshot: the screenshot is scoped so the pixel diff
    compares like with like against one Figma frame, whereas the DOM is
    search evidence, and an element just outside the frame is still the
    element a finding might be about.
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

            screenshot = await _screenshot(page, url, selector)
            dom = await extract_dom_snapshot(
                page, viewport_width=viewport_width, viewport_height=viewport_height
            )
            return PageCapture(screenshot=screenshot, dom=dom)
        finally:
            await browser.close()


async def _screenshot(page: Page, url: str, selector: str | None) -> bytes:
    if selector:
        locator = page.locator(selector)
        try:
            await locator.wait_for(state="visible", timeout=10_000)
        except PlaywrightTimeoutError as exc:
            raise PlaywrightCaptureError(f"selector {selector!r} not found on {url!r}") from exc
        return await locator.screenshot()

    return await page.screenshot(full_page=True)
