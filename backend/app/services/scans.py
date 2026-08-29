"""Scan orchestration: capture the target app, diff against the project's
stored Figma render, persist the result.

Plain async service calling integrations directly — no LangGraph/agent
involved yet, same as app.services.projects (see its module docstring).
The Visual Comparison *agent* (with LLM-backed interpretation of the diff)
is a later phase; this is the deterministic capture-and-diff step it will
eventually call as a tool.
"""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.axe.scan import run_accessibility_scan
from app.integrations.imaging.compare import compare_images
from app.integrations.playwright.breakpoints import (
    MATCH_FIGMA_BREAKPOINT,
    STANDARD_BREAKPOINTS,
    Viewport,
    match_figma_viewport,
)
from app.integrations.playwright.capture import capture_screenshot
from app.integrations.storage.base import StorageBackend
from app.models.project import Project
from app.models.scan import Scan
from app.schemas.scan import ScanCreate


class ScanTargetNotReadyError(Exception):
    """Raised when a project hasn't finished its Figma fetch yet."""


async def create_scan(
    db: AsyncSession, project: Project, payload: ScanCreate, storage: StorageBackend
) -> Scan:
    """Capture `project.target_url`, diff it against the stored Figma
    screenshot, and persist the result.

    Everything that can fail (capture, diff) happens before any row is
    added to the session, so a failure here simply raises without leaving
    a half-written scan — there's nothing to roll back.
    """
    if project.figma_screenshot_key is None:
        raise ScanTargetNotReadyError(
            "project has no Figma screenshot yet (registration may have failed)"
        )

    viewport_width, viewport_height = _resolve_viewport(payload, project)

    expected_png = storage.read(project.figma_screenshot_key)

    actual_png = await capture_screenshot(
        project.target_url,
        selector=project.target_selector,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
    )

    comparison_result, diff_png = compare_images(expected_png, actual_png)

    accessibility_report = await run_accessibility_scan(
        project.target_url,
        selector=project.target_selector,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
    )

    scan_id = uuid4()
    production_key = f"scans/{scan_id}/production.png"
    diff_key = f"scans/{scan_id}/diff.png"
    storage.save(production_key, actual_png)
    storage.save(diff_key, diff_png)

    scan = Scan(
        id=scan_id,
        project_id=project.id,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        breakpoint=payload.breakpoint,
        production_screenshot_key=production_key,
        diff_image_key=diff_key,
        comparison_result=comparison_result.model_dump(mode="json"),
        accessibility_report=accessibility_report.model_dump(mode="json"),
    )
    db.add(scan)
    await db.commit()
    await db.refresh(scan)
    return scan


async def create_scans_at_all_breakpoints(
    db: AsyncSession, project: Project, storage: StorageBackend
) -> list[Scan]:
    """Run create_scan() once per STANDARD_BREAKPOINTS entry, sequentially.

    Each scan commits independently (see create_scan's docstring), so a
    failure partway through still leaves the earlier breakpoints' scans
    persisted — this simply re-raises on the first failure rather than
    attempting partial-failure bookkeeping.
    """
    return [
        await create_scan(db, project, ScanCreate(breakpoint=name), storage)
        for name in STANDARD_BREAKPOINTS
    ]


async def list_scans(db: AsyncSession, project_id: UUID) -> list[Scan]:
    result = await db.execute(
        select(Scan).where(Scan.project_id == project_id).order_by(Scan.created_at.desc())
    )
    return list(result.scalars().all())


async def get_scan(db: AsyncSession, project_id: UUID, scan_id: UUID) -> Scan | None:
    result = await db.execute(
        select(Scan).where(Scan.id == scan_id, Scan.project_id == project_id)
    )
    return result.scalar_one_or_none()


def _resolve_viewport(payload: ScanCreate, project: Project) -> Viewport:
    if payload.breakpoint == MATCH_FIGMA_BREAKPOINT:
        return _match_figma_viewport(project)
    if payload.breakpoint is not None:
        return STANDARD_BREAKPOINTS[payload.breakpoint]
    return Viewport(payload.viewport_width, payload.viewport_height)


def _match_figma_viewport(project: Project) -> Viewport:
    """Scan-specific wrapper: a scan that explicitly asked for match_figma
    can't fall back to a default width, so a node with no recorded width
    is an error here rather than something to shrug off (contrast
    app.agents.production_analysis, which still wants a capture).
    """
    viewport = match_figma_viewport(project.figma_data or {})
    if viewport is None:
        raise ScanTargetNotReadyError(
            "project's Figma node has no recorded width; can't use match_figma"
        )
    return viewport
