from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.integrations.llm.exceptions import LLMNotConfiguredError, LLMResponseError
from app.integrations.playwright.exceptions import PlaywrightCaptureError
from app.integrations.storage.base import StorageBackend
from app.integrations.storage.local import get_storage_backend
from app.models.project import Project
from app.schemas.design_analysis import DesignAnalysisRead
from app.services import design_analysis as design_analysis_service
from app.services import projects as projects_service
from app.services.design_analysis import ProjectNotAnalyzableError

router = APIRouter(prefix="/projects/{project_id}/design-analysis", tags=["design-analysis"])


async def _get_project_or_404(project_id: UUID, db: AsyncSession) -> Project:
    project = await projects_service.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return project


@router.post("", response_model=DesignAnalysisRead, status_code=status.HTTP_201_CREATED)
async def create_design_analysis(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
) -> DesignAnalysisRead:
    project = await _get_project_or_404(project_id, db)
    try:
        analysis = await design_analysis_service.create_design_analysis(db, project, storage)
    except ProjectNotAnalyzableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except LLMResponseError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except PlaywrightCaptureError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return DesignAnalysisRead.model_validate(analysis)


@router.get("", response_model=list[DesignAnalysisRead])
async def list_design_analyses(
    project_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[DesignAnalysisRead]:
    await _get_project_or_404(project_id, db)
    analyses = await design_analysis_service.list_design_analyses(db, project_id)
    return [DesignAnalysisRead.model_validate(analysis) for analysis in analyses]


@router.get("/{design_analysis_id}/production")
async def get_design_analysis_production_screenshot(
    project_id: UUID,
    design_analysis_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
) -> Response:
    await _get_project_or_404(project_id, db)
    analysis = await design_analysis_service.get_design_analysis(db, project_id, design_analysis_id)
    if analysis is None or analysis.production_screenshot_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="design analysis not found"
        )
    return Response(
        content=storage.read(analysis.production_screenshot_key), media_type="image/png"
    )
