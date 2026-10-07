from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import require_current_user
from app.db.session import get_db
from app.integrations.llm.exceptions import LLMNotConfiguredError, LLMResponseError
from app.integrations.storage.base import StorageBackend
from app.integrations.storage.local import get_storage_backend
from app.models.project import Project
from app.models.scan import Scan
from app.models.user import User
from app.schemas.review import ReviewRead
from app.services import projects as projects_service
from app.services import reviews as reviews_service
from app.services import scans as scans_service

router = APIRouter(prefix="/projects/{project_id}/scans/{scan_id}/reviews", tags=["reviews"])


async def _get_scan_or_404(
    project_id: UUID, scan_id: UUID, db: AsyncSession, owner_id: UUID
) -> tuple[Project, Scan]:
    """The caller's project and one of its scans, or 404.

    The ownership check is on the project, and the scan is then looked up
    *within* it — so a scan id belonging to someone else's project can't be
    reached by pairing it with a project id you do own.
    """
    project = await projects_service.get_project(db, project_id, owner_id=owner_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    scan = await scans_service.get_scan(db, project_id, scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")
    return project, scan


@router.post("", response_model=ReviewRead, status_code=status.HTTP_201_CREATED)
async def create_review(
    project_id: UUID,
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
    user: User = Depends(require_current_user),
) -> ReviewRead:
    project, scan = await _get_scan_or_404(project_id, scan_id, db, user.id)
    try:
        review = await reviews_service.create_review(db, project, scan, storage)
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except LLMResponseError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return ReviewRead.model_validate(review)


@router.get("", response_model=list[ReviewRead])
async def list_reviews(
    project_id: UUID,
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
) -> list[ReviewRead]:
    await _get_scan_or_404(project_id, scan_id, db, user.id)
    reviews = await reviews_service.list_reviews(db, scan_id)
    return [ReviewRead.model_validate(review) for review in reviews]
