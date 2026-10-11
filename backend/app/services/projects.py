"""Project registration and Figma-fetch orchestration.

Plain async service functions calling the Figma client + storage backend
directly — no LangGraph/agent involved yet. That layer arrives in Phase 3+,
once there's an actual decision/routing step that needs it (per
docs/principles.md #6); until then this is a deterministic fetch-and-persist
flow, which is all "register a project" requires.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.integrations.figma.client import FigmaClient
from app.integrations.figma.exceptions import FigmaAPIError
from app.integrations.storage.base import StorageBackend
from app.models.design_analysis import DesignAnalysis
from app.models.project import Project
from app.models.scan import Scan
from app.schemas.project import ProjectCreate
from app.services.workspace import remove_project_workspaces
from app.tools.repo_search import SourceNotAccessibleError

logger = logging.getLogger(__name__)


async def create_project(
    db: AsyncSession, payload: ProjectCreate, storage: StorageBackend, owner_id: UUID
) -> Project:
    """Register a project and synchronously fetch/store its Figma data.

    `storage` is passed in (rather than resolved internally) so the route
    handler's storage dependency is the single source of truth for where
    artifacts live — the same backend used to write here is what a later
    read (e.g. the screenshot endpoint) will use.

    If the Figma fetch fails, nothing is persisted: the session is closed
    (rolled back) without a commit, so a project row is never left in a
    half-registered state.
    """
    project = Project(
        owner_id=owner_id,
        name=payload.name,
        figma_file_key=payload.figma_file_key,
        figma_node_id=payload.figma_node_id,
        target_url=str(payload.target_url),
        target_selector=payload.target_selector,
        source_path=payload.source_path,
        github_repo_full_name=payload.github_repo_full_name,
        github_branch=payload.github_branch,
    )
    db.add(project)
    await db.flush()  # assigns project.id, used below as a storage key

    await _fetch_and_store_figma_data(project, storage)

    await db.commit()
    await db.refresh(project)
    return project


async def list_projects(db: AsyncSession, owner_id: UUID) -> list[Project]:
    result = await db.execute(
        select(Project).where(Project.owner_id == owner_id).order_by(Project.created_at.desc())
    )
    return list(result.scalars().all())


async def get_project(db: AsyncSession, project_id: UUID, owner_id: UUID) -> Project | None:
    """One of `owner_id`'s projects, or None.

    `owner_id` is required rather than optional so that forgetting it is a
    type error instead of a silent authorization hole — the whole point of
    this function is that no caller can accidentally read across accounts.

    Returns None for "someone else's project" as well as for "no such
    project", so callers 404 both. A 403 would confirm the id exists,
    which tells an attacker holding a guessed UUID that they guessed right.

    When sharing arrives this is the one query that changes: the ownership
    test widens to "owns it OR is a member", and every route keeps working.
    """
    project = await db.get(Project, project_id)
    if project is None or project.owner_id != owner_id:
        return None
    return project


async def _fetch_and_store_figma_data(project: Project, storage: StorageBackend) -> None:
    settings = get_settings()
    if not settings.figma_access_token:
        raise FigmaAPIError("FIGMA_ACCESS_TOKEN is not configured")

    client = FigmaClient(
        access_token=settings.figma_access_token, base_url=settings.figma_api_base_url
    )
    try:
        node = await client.get_node(project.figma_file_key, project.figma_node_id)
        image_url = await client.get_image_url(project.figma_file_key, project.figma_node_id)
        image_bytes = await client.download_image(image_url)
    finally:
        await client.aclose()

    screenshot_key = f"figma/{project.id}/preview.png"
    storage.save(screenshot_key, image_bytes)

    project.figma_data = node.model_dump(mode="json")
    project.figma_screenshot_key = screenshot_key
    project.figma_fetched_at = datetime.now(UTC)


async def delete_project(db: AsyncSession, project: Project, storage: StorageBackend) -> None:
    """Remove a project and everything it produced.

    Rows cascade (scans -> reviews, and design analyses), but the files do
    not: storage artifacts and cloned workspaces are referenced by keys on
    those rows, so they have to be collected *before* the delete or they
    become unreachable litter — a deleted project would silently keep its
    screenshots and a full third-party checkout on disk.

    Files are removed before the commit, but a failure to unlink one does
    not abort the delete: the user asked for the project to go, and leaving
    the row behind because a screenshot was already missing would be the
    worse outcome. Storage.delete is a no-op on an absent key for the same
    reason.
    """
    keys = await _artifact_keys(db, project)

    for key in keys:
        try:
            storage.delete(key)
        except (OSError, ValueError) as exc:
            # ValueError: a key that escapes the storage root, which should
            # be impossible for keys we wrote — logged, not raised.
            logger.warning("could not delete artifact %s: %s", key, exc)

    try:
        remove_project_workspaces(project.id)
    except (OSError, SourceNotAccessibleError) as exc:
        logger.warning("could not remove workspaces for project %s: %s", project.id, exc)

    await db.delete(project)
    await db.commit()


async def _artifact_keys(db: AsyncSession, project: Project) -> list[str]:
    """Every storage key this project owns, across its rows."""
    keys: list[str | None] = [project.figma_screenshot_key]

    scans = (await db.execute(select(Scan).where(Scan.project_id == project.id))).scalars().all()
    for scan in scans:
        keys += [scan.production_screenshot_key, scan.diff_image_key]

    analyses = (
        (await db.execute(select(DesignAnalysis).where(DesignAnalysis.project_id == project.id)))
        .scalars()
        .all()
    )
    for analysis in analyses:
        keys += [
            analysis.production_screenshot_key,
            analysis.diff_image_key,
            analysis.verification_screenshot_key,
            analysis.verification_diff_image_key,
        ]

    # Deduplicated: a re-run can record the same key twice, and deleting it
    # twice is harmless but noisy in the logs.
    return list(dict.fromkeys(key for key in keys if key))
