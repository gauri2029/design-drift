"""Unit tests for app.services.scans's viewport resolution — no browser,
no DB, just the pure logic that decides what viewport a scan uses.
"""

import pytest

from app.integrations.playwright.breakpoints import (
    MATCH_FIGMA_VIEWPORT_HEIGHT,
    STANDARD_BREAKPOINTS,
    Viewport,
)
from app.models.project import Project
from app.schemas.scan import ScanCreate
from app.services.scans import ScanTargetNotReadyError, _match_figma_viewport, _resolve_viewport


def _project_with_figma_width(width: float | None) -> Project:
    # Matches the *actual* stored shape: project.figma_data is
    # FigmaNode.model_dump(mode="json") with no by_alias=True, so the key
    # is the model's field name (snake_case), not the API's camelCase
    # alias — see _match_figma_viewport's comment on this.
    figma_data = (
        {"absolute_bounding_box": {"width": width, "height": 6599.0}} if width is not None else {}
    )
    return Project(
        name="test",
        figma_file_key="key",
        figma_node_id="1:1",
        target_url="https://example.com",
        figma_data=figma_data,
    )


def test_match_figma_uses_the_figma_frame_width() -> None:
    project = _project_with_figma_width(1400.0)

    assert _match_figma_viewport(project) == Viewport(1400, MATCH_FIGMA_VIEWPORT_HEIGHT)


@pytest.mark.parametrize(
    ("figma_width", "expected_viewport_width"),
    [
        (1400.4, 1400),  # rounds down
        (1400.6, 1401),  # rounds up — proves round(), not int()/truncation
    ],
)
def test_match_figma_rounds_float_width_instead_of_truncating(
    figma_width: float, expected_viewport_width: int
) -> None:
    project = _project_with_figma_width(figma_width)

    viewport = _match_figma_viewport(project)

    assert viewport.width == expected_viewport_width


def test_match_figma_height_is_a_normal_viewport_height_not_the_figma_frame_height() -> None:
    # The Figma frame in _project_with_figma_width is 1400 x 6599 — a full
    # long page. The resolved viewport height must NOT be 6599: match_figma
    # relies on full_page capture for height, not the viewport itself.
    project = _project_with_figma_width(1400.0)

    viewport = _match_figma_viewport(project)

    assert viewport.height == MATCH_FIGMA_VIEWPORT_HEIGHT
    assert viewport.height != 6599


def test_match_figma_raises_when_figma_node_has_no_recorded_width() -> None:
    project = _project_with_figma_width(None)

    with pytest.raises(ScanTargetNotReadyError, match="no recorded width"):
        _match_figma_viewport(project)


def test_match_figma_raises_when_project_has_no_figma_data_at_all() -> None:
    project = Project(
        name="test",
        figma_file_key="key",
        figma_node_id="1:1",
        target_url="https://example.com",
        figma_data=None,
    )

    with pytest.raises(ScanTargetNotReadyError, match="no recorded width"):
        _match_figma_viewport(project)


@pytest.mark.parametrize("name", list(STANDARD_BREAKPOINTS))
def test_resolve_viewport_standard_presets_are_unchanged(name: str) -> None:
    project = _project_with_figma_width(1400.0)

    viewport = _resolve_viewport(ScanCreate(breakpoint=name), project)

    assert viewport == STANDARD_BREAKPOINTS[name]


def test_resolve_viewport_match_figma_delegates_to_match_figma_viewport() -> None:
    project = _project_with_figma_width(1234.0)

    viewport = _resolve_viewport(ScanCreate(breakpoint="match_figma"), project)

    assert viewport == Viewport(1234, MATCH_FIGMA_VIEWPORT_HEIGHT)


def test_resolve_viewport_with_no_breakpoint_uses_payload_dimensions() -> None:
    project = _project_with_figma_width(1400.0)

    viewport = _resolve_viewport(ScanCreate(viewport_width=999, viewport_height=555), project)

    assert viewport == Viewport(999, 555)
