from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import require_current_user
from app.db.session import get_db
from app.integrations.playwright.exceptions import PlaywrightCaptureError
from app.integrations.storage.base import StorageBackend
from app.integrations.storage.local import get_storage_backend
from app.models.project import Project
from app.models.user import User
from app.schemas.scan import ScanCreate, ScanRead
from app.services import projects as projects_service
from app.services import scans as scans_service
from app.services.scans import ScanTargetNotReadyError

router = APIRouter(prefix="/projects/{project_id}/scans", tags=["scans"])


async def _get_project_or_404(project_id: UUID, db: AsyncSession, owner_id: UUID) -> Project:
    """The caller's project, or 404.

    Someone else's project is a 404 rather than a 403: a 403 would confirm
    the id names a real project, which is exactly what a guessed UUID is
    trying to find out.
    """
    project = await projects_service.get_project(db, project_id, owner_id=owner_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return project


@router.post("", response_model=ScanRead, status_code=status.HTTP_201_CREATED)
async def create_scan(
    project_id: UUID,
    payload: ScanCreate | None = None,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
    user: User = Depends(require_current_user),
) -> ScanRead:
    project = await _get_project_or_404(project_id, db, user.id)
    try:
        scan = await scans_service.create_scan(db, project, payload or ScanCreate(), storage)
    except ScanTargetNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PlaywrightCaptureError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return ScanRead.model_validate(scan)


@router.post("/breakpoints", response_model=list[ScanRead], status_code=status.HTTP_201_CREATED)
async def create_scans_at_all_breakpoints(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
    user: User = Depends(require_current_user),
) -> list[ScanRead]:
    """Run one scan per standard breakpoint (mobile/tablet/desktop).

    Scans that complete before a failure stay persisted — see
    scans_service.create_scans_at_all_breakpoints's docstring.
    """
    project = await _get_project_or_404(project_id, db, user.id)
    try:
        scans = await scans_service.create_scans_at_all_breakpoints(db, project, storage)
    except ScanTargetNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PlaywrightCaptureError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [ScanRead.model_validate(scan) for scan in scans]


@router.get("", response_model=list[ScanRead])
async def list_scans(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
) -> list[ScanRead]:
    await _get_project_or_404(project_id, db, user.id)
    scans = await scans_service.list_scans(db, project_id)
    return [ScanRead.model_validate(scan) for scan in scans]


@router.get("/{scan_id}", response_model=ScanRead)
async def get_scan(
    project_id: UUID,
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
) -> ScanRead:
    await _get_project_or_404(project_id, db, user.id)
    scan = await scans_service.get_scan(db, project_id, scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")
    return ScanRead.model_validate(scan)


@router.get("/{scan_id}/production")
async def get_scan_production_screenshot(
    project_id: UUID,
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
    user: User = Depends(require_current_user),
) -> Response:
    await _get_project_or_404(project_id, db, user.id)
    scan = await scans_service.get_scan(db, project_id, scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")
    return Response(content=storage.read(scan.production_screenshot_key), media_type="image/png")


@router.get("/{scan_id}/diff")
async def get_scan_diff_image(
    project_id: UUID,
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
    user: User = Depends(require_current_user),
) -> Response:
    await _get_project_or_404(project_id, db, user.id)
    scan = await scans_service.get_scan(db, project_id, scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")
    return Response(content=storage.read(scan.diff_image_key), media_type="image/png")
