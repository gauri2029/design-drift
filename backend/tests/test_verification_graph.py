"""Graph tests for the verification pass (app.graph.verification_workflow).

The two things worth pinning here are the ones a reader can't see from the
node code alone: the deterministic delta is set arithmetic over rule ids,
and an unchanged page never reaches the paid LLM call.

Playwright and axe are stubbed rather than driven for real — what's under
test is the routing and the arithmetic, and "is this capture identical to
that one" can't be asserted against a real browser without depending on
byte-level render determinism. The real capture path runs in
test_design_analysis_api.py.
"""

import uuid
from io import BytesIO

import pytest
import respx
from PIL import Image
from respx import MockRouter

from app.agents.recapture import accessibility_delta
from app.core.config import get_settings
from app.graph.verification_state import VerificationState
from app.graph.verification_workflow import run_verification
from app.integrations.axe.types import AccessibilityReport, AxeViolation
from app.integrations.imaging.types import ComparisonResult, ImageDimensions
from tests.conftest import mock_anthropic_by_agent

VERIFICATION_JUDGMENT = {
    "summary": "The language attribute is now set.",
    "findings": [
        {
            "finding_title": "html-has-lang",
            "verdict": "resolved",
            "explanation": "axe no longer reports the rule.",
        }
    ],
    "regressions": [],
}


def _png(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _report(*rule_ids: str) -> AccessibilityReport:
    violations = [
        AxeViolation(id=rule_id, description="d", help="h", helpUrl="https://example.test")
        for rule_id in rule_ids
    ]
    return AccessibilityReport(violations=violations, violation_count=len(violations))


def _comparison(percentage: float) -> ComparisonResult:
    dimensions = ImageDimensions(width=10, height=10)
    return ComparisonResult(
        expected_dimensions=dimensions,
        actual_dimensions=dimensions,
        dimensions_match=True,
        compared_dimensions=dimensions,
        mismatched_pixels=int(percentage),
        total_pixels=100,
        mismatch_percentage=percentage,
    )


def _state(before_screenshot: bytes) -> VerificationState:
    return VerificationState(
        project_id=uuid.uuid4(),
        figma_node={"absolute_bounding_box": {"width": 400, "height": 300}},
        figma_screenshot=_png((400, 300), (255, 255, 255)),
        target_url="http://example.test/",
        before_screenshot=before_screenshot,
        before_comparison=_comparison(12.0),
        before_accessibility=_report("html-has-lang", "region"),
    )


def test_the_accessibility_delta_is_set_arithmetic_over_rule_ids() -> None:
    delta = accessibility_delta(
        _report("html-has-lang", "region"), _report("region", "color-contrast")
    )

    assert delta.resolved_rule_ids == ["html-has-lang"]
    assert delta.remaining_rule_ids == ["region"]
    # The signal most worth a human's attention: the change broke something.
    assert delta.new_rule_ids == ["color-contrast"]


@pytest.fixture
def stub_capture(monkeypatch):
    """Replace the browser/axe tools the recapture node calls."""

    def configure(screenshot: bytes, report: AccessibilityReport) -> None:
        async def capture(*args, **kwargs) -> bytes:
            return screenshot

        async def scan(*args, **kwargs) -> AccessibilityReport:
            return report

        monkeypatch.setattr("app.agents.recapture.capture_screenshot", capture)
        monkeypatch.setattr("app.agents.recapture.run_accessibility_scan", scan)

    return configure


@respx.mock
async def test_an_unchanged_page_is_reported_as_such_without_a_paid_call(
    monkeypatch, stub_capture
) -> None:
    """A deployed target that hasn't been rebuilt yet looks exactly like a
    fix that did nothing. Saying so is the honest answer, and there is
    nothing for a model to judge."""
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-anthropic-key")
    unchanged = _png((400, 300), (0, 0, 0))
    stub_capture(unchanged, _report("html-has-lang", "region"))
    anthropic = respx.post("https://api.anthropic.com/v1/messages")

    final = await run_verification(_state(unchanged))

    assert final.verification is not None
    assert final.verification.production_changed is False
    assert final.verification.findings == []
    assert "rebuilding" in final.verification.summary
    assert anthropic.call_count == 0


@respx.mock
async def test_a_changed_page_is_judged_against_the_measurements(monkeypatch, stub_capture) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-anthropic-key")
    stub_capture(_png((400, 300), (255, 255, 255)), _report("region"))
    route: MockRouter = mock_anthropic_by_agent({"verification": VERIFICATION_JUDGMENT})

    final = await run_verification(_state(_png((400, 300), (0, 0, 0))))

    assert route.call_count == 1
    assert final.verification is not None
    assert final.verification.production_changed is True
    assert final.verification.findings[0].verdict == "resolved"
    # The judgment carries the measurements it was made from, so a reader
    # can check the verdict rather than take it on trust.
    assert final.verification.mismatch_percentage_before == 12.0
    assert final.verification.accessibility_delta.resolved_rule_ids == ["html-has-lang"]
    assert final.after_diff_screenshot is not None
