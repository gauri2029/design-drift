"""Project registration and Figma-fetch orchestration.

Plain async service functions calling the Figma client + storage backend
directly — no LangGraph/agent involved yet. That layer arrives in Phase 3+,
once there's an actual decision/routing step that needs it (per
docs/principles.md #6); until then this is a deterministic fetch-and-persist
flow, which is all "register a project" requires.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.integrations.figma.client import FigmaClient
from app.integrations.figma.exceptions import FigmaAPIError
from app.integrations.storage.base import StorageBackend
from app.models.project import Project
from app.schemas.project import ProjectCreate


async def create_project(
    db: AsyncSession, payload: ProjectCreate, storage: StorageBackend
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
        name=payload.name,
        figma_file_key=payload.figma_file_key,
        figma_node_id=payload.figma_node_id,
        target_url=str(payload.target_url),
    )
    db.add(project)
    await db.flush()  # assigns project.id, used below as a storage key

    await _fetch_and_store_figma_data(project, storage)

    await db.commit()
    await db.refresh(project)
    return project


async def list_projects(db: AsyncSession) -> list[Project]:
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return list(result.scalars().all())


async def get_project(db: AsyncSession, project_id: UUID) -> Project | None:
    return await db.get(Project, project_id)


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
