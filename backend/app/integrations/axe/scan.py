"""Deterministic accessibility scanning via axe-core.

No LLM here — axe-core answers "which accessibility rules are violated"
deterministically (per docs/principles.md #2). axe.min.js ships inside the
axe-playwright-python package, so this runs fully offline. Interpreting or
prioritizing violations in context is a judgment call that belongs to the
visual-reasoning layer (app.services.findings), not this module.
"""

from axe_playwright_python.async_playwright import Axe
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from app.integrations.axe.exceptions import AccessibilityScanError
from app.integrations.axe.types import AccessibilityReport

_axe = Axe()


async def run_accessibility_scan(
    url: str,
    *,
    selector: str | None = None,
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> AccessibilityReport:
    """Run axe-core against `url`, optionally scoped to one element.

    A fresh browser is launched per call, matching
    app.integrations.playwright.capture.capture_screenshot's rationale.
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height}
            )
            page = await context.new_page()

            try:
                await page.goto(url)
            except PlaywrightError as exc:
                raise AccessibilityScanError(f"failed to load {url!r}: {exc}") from exc

            results = await _axe.run(page, context=selector)
        finally:
            await browser.close()

    violations = results.response["violations"]
    return AccessibilityReport(violations=violations, violation_count=len(violations))
