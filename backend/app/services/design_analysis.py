"""Design Analysis Agent orchestration: assemble inputs from a project's
stored Figma data, run the LangGraph workflow, persist the result.

Unlike app.services.projects/scans (plain service functions calling
integrations directly, per those modules' docstrings), this is the first
place an actual LangGraph graph runs — see app.graph.workflow for the
graph itself and docs/architecture.md for where this fits in the target
multi-agent workflow.

Like app.services.reviews, this is never triggered automatically — it
costs real money per call, so it's an explicit action the frontend gates
behind a button.
"""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.graph.state import DesignAnalysisState
from app.graph.workflow import run_design_analysis
from app.integrations.storage.base import StorageBackend
from app.models.design_analysis import DesignAnalysis
from app.models.project import Project


class ProjectNotAnalyzableError(Exception):
    """Raised when a project has no usable Figma data yet to analyze."""


async def create_design_analysis(
    db: AsyncSession, project: Project, storage: StorageBackend
) -> DesignAnalysis:
    if project.figma_screenshot_key is None:
        raise ProjectNotAnalyzableError(
            "project has no Figma screenshot yet (registration may have failed)"
        )

    initial_state = DesignAnalysisState(
        project_id=project.id,
        figma_node=project.figma_data or {},
        figma_screenshot=storage.read(project.figma_screenshot_key),
    )
    final_state = await run_design_analysis(initial_state)

    if final_state.error is not None:
        raise ProjectNotAnalyzableError(final_state.error)
    assert final_state.result is not None  # guaranteed by route_after_supervisor

    settings = get_settings()
    design_analysis = DesignAnalysis(
        id=uuid4(),
        project_id=project.id,
        model=settings.anthropic_model,
        result=final_state.result.model_dump(mode="json"),
    )
    db.add(design_analysis)
    await db.commit()
    await db.refresh(design_analysis)
    return design_analysis


async def list_design_analyses(db: AsyncSession, project_id: UUID) -> list[DesignAnalysis]:
    result = await db.execute(
        select(DesignAnalysis)
        .where(DesignAnalysis.project_id == project_id)
        .order_by(DesignAnalysis.created_at.desc())
    )
    return list(result.scalars().all())
