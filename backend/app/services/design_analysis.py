"""Design QA workflow orchestration: assemble inputs from a project (its
stored Figma data, its target app), run the LangGraph workflow, persist
the result.

Unlike app.services.projects/scans (plain service functions calling
integrations directly, per those modules' docstrings), this is the first
place an actual LangGraph graph runs — see app.graph.workflow for the
graph itself and docs/architecture.md for where this fits in the target
multi-agent workflow. The graph currently runs Design Analysis, then
Production Analysis, then Visual Comparison, then Accessibility (see
app.graph.state.DesignQAState); this function's name/table stay
"design_analysis" rather than being renamed each time the graph gains an
agent, same as Scan's name didn't change when breakpoints were added to it.

Like app.services.reviews, this is never triggered automatically — it
costs real money and launches a real browser per call, so it's an
explicit action the frontend gates behind a button.
"""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.graph.state import DesignQAState
from app.graph.workflow import run_design_qa
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

    initial_state = DesignQAState(
        project_id=project.id,
        figma_node=project.figma_data or {},
        figma_screenshot=storage.read(project.figma_screenshot_key),
        target_url=project.target_url,
        target_selector=project.target_selector,
    )
    final_state = await run_design_qa(initial_state)

    if final_state.error is not None:
        raise ProjectNotAnalyzableError(final_state.error)
    # All guaranteed by route_after_supervisor: it only routes to END once
    # none of these are None (or on error, handled above).
    assert final_state.design_analysis is not None
    assert final_state.production_screenshot is not None
    assert final_state.comparison_result is not None
    assert final_state.diff_screenshot is not None
    assert final_state.visual_comparison is not None
    assert final_state.accessibility_report is not None
    assert final_state.accessibility_interpretation is not None

    analysis_id = uuid4()
    production_screenshot_key = f"design-analyses/{analysis_id}/production.png"
    diff_image_key = f"design-analyses/{analysis_id}/diff.png"
    storage.save(production_screenshot_key, final_state.production_screenshot)
    storage.save(diff_image_key, final_state.diff_screenshot)

    settings = get_settings()
    design_analysis = DesignAnalysis(
        id=analysis_id,
        project_id=project.id,
        model=settings.llm_model,
        result=final_state.design_analysis.model_dump(mode="json"),
        production_screenshot_key=production_screenshot_key,
        comparison_result=final_state.comparison_result.model_dump(mode="json"),
        diff_image_key=diff_image_key,
        visual_comparison=final_state.visual_comparison.model_dump(mode="json"),
        accessibility_report=final_state.accessibility_report.model_dump(mode="json"),
        accessibility_interpretation=final_state.accessibility_interpretation.model_dump(
            mode="json"
        ),
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


async def get_design_analysis(
    db: AsyncSession, project_id: UUID, design_analysis_id: UUID
) -> DesignAnalysis | None:
    result = await db.execute(
        select(DesignAnalysis).where(
            DesignAnalysis.id == design_analysis_id, DesignAnalysis.project_id == project_id
        )
    )
    return result.scalar_one_or_none()
