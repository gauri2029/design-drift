"""axe-core accessibility scan tests, against a local static fixture."""

from pathlib import Path

import pytest

from app.integrations.axe.exceptions import AccessibilityScanError
from app.integrations.axe.scan import run_accessibility_scan

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "accessibility_fixture.html").as_uri()


async def test_whole_page_scan_finds_both_violations() -> None:
    report = await run_accessibility_scan(FIXTURE_URL)

    ids = {violation.id for violation in report.violations}
    assert "image-alt" in ids
    assert "button-name" in ids
    assert report.violation_count == len(report.violations)


async def test_selector_scoped_scan_excludes_violations_outside_it() -> None:
    report = await run_accessibility_scan(FIXTURE_URL, selector="#card")

    ids = {violation.id for violation in report.violations}
    assert "button-name" in ids
    assert "image-alt" not in ids  # outside #card, so out of scope


async def test_raises_when_navigation_fails() -> None:
    with pytest.raises(AccessibilityScanError, match="failed to load"):
        await run_accessibility_scan("file:///no/such/fixture.html")
