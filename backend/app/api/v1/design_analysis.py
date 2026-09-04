from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.integrations.axe.exceptions import AccessibilityScanError
from app.integrations.llm.exceptions import LLMNotConfiguredError, LLMResponseError
from app.integrations.playwright.exceptions import PlaywrightCaptureError
from app.integrations.storage.base import StorageBackend
from app.integrations.storage.local import get_storage_backend
from app.models.project import Project
from app.schemas.design_analysis import DesignAnalysisRead
from app.schemas.fix_review import FixReviewRequest
from app.schemas.verification import VerificationRequest
from app.services import design_analysis as design_analysis_service
from app.services import projects as projects_service
from app.services import verification as verification_service
from app.services.design_analysis import (
    FixApplicationError,
    FixReviewError,
    ProjectNotAnalyzableError,
)
from app.services.verification import NotVerifiableError
from app.tools.repo_search import SourceNotAccessibleError

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
    except SourceNotAccessibleError as exc:
        # 409, not 502: the project's own source_path is misconfigured —
        # a state-of-this-resource problem the user can fix, not an
        # upstream service failing.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except LLMResponseError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except PlaywrightCaptureError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except AccessibilityScanError as exc:
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


@router.get("/{design_analysis_id}/diff")
async def get_design_analysis_diff_image(
    project_id: UUID,
    design_analysis_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
) -> Response:
    await _get_project_or_404(project_id, db)
    analysis = await design_analysis_service.get_design_analysis(db, project_id, design_analysis_id)
    if analysis is None or analysis.diff_image_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="design analysis not found"
        )
    return Response(content=storage.read(analysis.diff_image_key), media_type="image/png")


@router.put("/{design_analysis_id}/fix-review", response_model=DesignAnalysisRead)
async def review_design_analysis_fixes(
    project_id: UUID,
    design_analysis_id: UUID,
    request: FixReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> DesignAnalysisRead:
    """The human-review pause in docs/architecture.md's workflow.

    PUT, not POST: a review is one current answer per run, and a reviewer
    changing their mind replaces it rather than adding a second one.
    """
    await _get_project_or_404(project_id, db)
    analysis = await design_analysis_service.get_design_analysis(db, project_id, design_analysis_id)
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="design analysis not found"
        )
    try:
        analysis = await design_analysis_service.review_fix_proposal(
            db, analysis, request.decisions
        )
    except FixReviewError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return DesignAnalysisRead.model_validate(analysis)


@router.post("/{design_analysis_id}/apply", response_model=DesignAnalysisRead)
async def apply_design_analysis_fixes(
    project_id: UUID,
    design_analysis_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DesignAnalysisRead:
    """Write this run's approved patches into the project's source checkout.

    POST, not PUT: applying is an event that happens once, not a value
    being set. It writes files and nothing else — no git, ever
    (docs/principles.md #5).
    """
    project = await _get_project_or_404(project_id, db)
    analysis = await design_analysis_service.get_design_analysis(db, project_id, design_analysis_id)
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="design analysis not found"
        )
    try:
        analysis = await design_analysis_service.apply_fix_review(db, project, analysis)
    except FixApplicationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SourceNotAccessibleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return DesignAnalysisRead.model_validate(analysis)


@router.post("/{design_analysis_id}/verify", response_model=DesignAnalysisRead)
async def verify_design_analysis(
    project_id: UUID,
    design_analysis_id: UUID,
    request: VerificationRequest | None = None,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
) -> DesignAnalysisRead:
    """Re-measure the page and judge whether the applied patches worked.

    Launches a browser and makes a paid LLM call, same as running the
    workflow, so it's an explicit action rather than something that
    follows applying automatically.
    """
    project = await _get_project_or_404(project_id, db)
    analysis = await design_analysis_service.get_design_analysis(db, project_id, design_analysis_id)
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="design analysis not found"
        )
    try:
        analysis = await verification_service.verify_design_analysis(
            db,
            project,
            analysis,
            storage,
            target_url=request.target_url if request else None,
        )
    except NotVerifiableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except LLMResponseError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except PlaywrightCaptureError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except AccessibilityScanError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return DesignAnalysisRead.model_validate(analysis)


@router.get("/{design_analysis_id}/verification-production")
async def get_verification_production_screenshot(
    project_id: UUID,
    design_analysis_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
) -> Response:
    await _get_project_or_404(project_id, db)
    analysis = await design_analysis_service.get_design_analysis(db, project_id, design_analysis_id)
    if analysis is None or analysis.verification_screenshot_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="verification not found")
    return Response(
        content=storage.read(analysis.verification_screenshot_key), media_type="image/png"
    )


@router.get("/{design_analysis_id}/verification-diff")
async def get_verification_diff_image(
    project_id: UUID,
    design_analysis_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
) -> Response:
    await _get_project_or_404(project_id, db)
    analysis = await design_analysis_service.get_design_analysis(db, project_id, design_analysis_id)
    if analysis is None or analysis.verification_diff_image_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="verification not found")
    return Response(
        content=storage.read(analysis.verification_diff_image_key), media_type="image/png"
    )
