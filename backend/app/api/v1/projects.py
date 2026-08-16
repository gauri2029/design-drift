from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.integrations.figma.exceptions import FigmaAPIError
from app.integrations.storage.base import StorageBackend
from app.integrations.storage.local import get_storage_backend
from app.schemas.project import ProjectCreate, ProjectRead
from app.services import projects as projects_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
) -> ProjectRead:
    try:
        project = await projects_service.create_project(db, payload, storage)
    except FigmaAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return ProjectRead.model_validate(project)


@router.get("", response_model=list[ProjectRead])
async def list_projects(db: AsyncSession = Depends(get_db)) -> list[ProjectRead]:
    projects = await projects_service.list_projects(db)
    return [ProjectRead.model_validate(project) for project in projects]


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: UUID, db: AsyncSession = Depends(get_db)) -> ProjectRead:
    project = await projects_service.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return ProjectRead.model_validate(project)


@router.get("/{project_id}/figma/screenshot")
async def get_project_figma_screenshot(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
) -> Response:
    project = await projects_service.get_project(db, project_id)
    if project is None or project.figma_screenshot_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="screenshot not found")

    data = storage.read(project.figma_screenshot_key)
    return Response(content=data, media_type="image/png")
