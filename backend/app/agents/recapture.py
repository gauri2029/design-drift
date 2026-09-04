"""The deterministic half of verification: capture the page again, scan it
again, diff it again. No LLM (docs/principles.md #2) — "what does the page
look like now" and "which axe rules fail now" are measurements, and the
judgment about whether that means a finding is fixed belongs to the
Verification Agent that reads them.

Deliberately the same three tools, at the same viewport, as the original
run's Production Analysis, Accessibility, and Visual Comparison steps.
Verification only means something if before and after were measured the
same way; a different capture width would show up as a change the patch
didn't cause.
"""

from typing import Any

from app.agents.production_analysis import FALLBACK_VIEWPORT
from app.agents.types import AccessibilityDelta, VerificationResult
from app.graph.verification_state import VerificationState
from app.integrations.axe.scan import run_accessibility_scan
from app.integrations.axe.types import AccessibilityReport
from app.integrations.imaging.compare import compare_images
from app.integrations.playwright.breakpoints import match_figma_viewport
from app.integrations.playwright.capture import capture_screenshot

UNCHANGED_SUMMARY = (
    "The page is byte-for-byte identical to the one captured during the original run, so "
    "nothing about it can have been affected by the patches. If the target URL is a "
    "deployed site, it needs rebuilding and redeploying before verification can say "
    "anything; if it's a local dev server, the patched files may not have been picked up."
)


async def recapture_node(state: VerificationState) -> dict[str, Any]:
    viewport = match_figma_viewport(state.figma_node) or FALLBACK_VIEWPORT

    after_screenshot = await capture_screenshot(
        state.target_url,
        selector=state.target_selector,
        viewport_width=viewport.width,
        viewport_height=viewport.height,
    )
    after_accessibility = await run_accessibility_scan(
        state.target_url, selector=state.target_selector
    )
    after_comparison, after_diff = compare_images(state.figma_screenshot, after_screenshot)

    update: dict[str, Any] = {
        "after_screenshot": after_screenshot,
        "after_accessibility": after_accessibility,
        "after_comparison": after_comparison,
        "after_diff_screenshot": after_diff,
    }

    # Nothing changed: answer it here rather than paying for a model to
    # look at two identical images and reach the same conclusion. Same
    # shortcut the Accessibility Agent takes when axe finds no violations,
    # and it's what routes the graph straight to END.
    if after_screenshot == state.before_screenshot:
        update["verification"] = VerificationResult(
            summary=UNCHANGED_SUMMARY,
            findings=[],
            regressions=[],
            accessibility_delta=accessibility_delta(
                state.before_accessibility, after_accessibility
            ),
            mismatch_percentage_before=state.before_comparison.mismatch_percentage,
            mismatch_percentage_after=after_comparison.mismatch_percentage,
            production_changed=False,
        )
    return update


def accessibility_delta(
    before: AccessibilityReport, after: AccessibilityReport
) -> AccessibilityDelta:
    """Set arithmetic over axe-core rule ids — exact, so computed, not asked.

    Rule ids rather than individual element violations: a rule that still
    fails on one element out of five isn't resolved, and collapsing to the
    rule keeps that honest.
    """
    before_ids = {violation.id for violation in before.violations}
    after_ids = {violation.id for violation in after.violations}
    return AccessibilityDelta(
        resolved_rule_ids=sorted(before_ids - after_ids),
        remaining_rule_ids=sorted(before_ids & after_ids),
        new_rule_ids=sorted(after_ids - before_ids),
    )
