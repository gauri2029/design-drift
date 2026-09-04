"""Tests for app.integrations.playwright.dom against a real browser.

Driven for real rather than stubbed: what's under test is what Chromium
reports about a rendered page — computed styles, box geometry, what counts
as visible — and a stub asserting my own assumptions about that would
prove nothing.
"""

from app.integrations.playwright.capture import capture_page
from app.integrations.playwright.dom import DomSnapshot


def _by_id(snapshot: DomSnapshot, element_id: str):
    return next(element for element in snapshot.elements if element.element_id == element_id)


async def _snapshot(fixture_server) -> DomSnapshot:
    host, port = fixture_server.server_address[:2]
    capture = await capture_page(f"http://{host}:{port}/dom_fixture.html")
    return capture.dom


async def test_an_element_carries_its_identity_text_and_rendered_styles(fixture_server) -> None:
    snapshot = await _snapshot(fixture_server)
    cta = _by_id(snapshot, "hero-cta")

    assert cta.tag == "a"
    assert cta.classes == ["cta", "button-primary"]
    assert cta.text == "Links"
    # Computed, not authored: this is what the browser actually rendered,
    # which is the only thing a Figma render can disagree with.
    assert cta.styles["color"] == "rgb(255, 255, 255)"
    assert cta.styles["font-size"] == "24px"
    assert cta.box.width > 0


async def test_text_is_the_elements_own_not_its_descendants(fixture_server) -> None:
    """Otherwise every wrapper carries the whole page and identifies nothing."""
    snapshot = await _snapshot(fixture_server)
    main = next(element for element in snapshot.elements if element.tag == "main")

    assert main.text is None
    assert _by_id(snapshot, "page-title").text == "Twenty Years of CNS"


async def test_elements_that_are_not_rendered_are_left_out(fixture_server) -> None:
    """An invisible element can't cause a visual difference, and its
    styles would be misleading evidence about one."""
    snapshot = await _snapshot(fixture_server)
    texts = [element.text for element in snapshot.elements]

    assert "Invisible copy" not in texts
    assert "Collapsed copy" not in texts


async def test_an_accessible_name_is_captured_where_there_is_no_text(fixture_server) -> None:
    snapshot = await _snapshot(fixture_server)

    assert _by_id(snapshot, "logo").accessible_name == "CNS logo"


async def test_the_screenshot_and_the_dom_come_from_one_page_load(fixture_server) -> None:
    host, port = fixture_server.server_address[:2]

    capture = await capture_page(
        f"http://{host}:{port}/dom_fixture.html", viewport_width=900, viewport_height=600
    )

    assert capture.screenshot.startswith(b"\x89PNG")
    assert capture.dom.viewport_width == 900
    assert capture.dom.elements


async def test_the_dom_covers_the_page_even_when_the_screenshot_is_scoped(
    fixture_server,
) -> None:
    """The screenshot is scoped so the pixel diff compares like with like;
    the DOM is search evidence, and an element outside the frame is still
    one a finding might be about."""
    host, port = fixture_server.server_address[:2]

    capture = await capture_page(f"http://{host}:{port}/dom_fixture.html", selector="#hero-cta")

    assert _by_id(capture.dom, "page-title").text == "Twenty Years of CNS"
