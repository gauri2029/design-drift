"""Runs the verification graph against a run whose patches were applied.

Kept out of app.services.design_analysis for the same reason the graph is
separate (see app.graph.verification_state): this is a second, later act
against the same row, with its own preconditions and its own failure
modes, not another step of the original run.

Like create_design_analysis, it launches a real browser and costs a real
LLM call, so it's an explicit user action rather than something that
happens automatically after applying.
"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.types import AggregatedFinding, AggregatedFindings
from app.graph.verification_state import VerificationState
from app.graph.verification_workflow import run_verification
from app.integrations.axe.types import AccessibilityReport
from app.integrations.imaging.types import ComparisonResult
from app.integrations.storage.base import StorageBackend
from app.models.design_analysis import DesignAnalysis
from app.models.project import Project
from app.schemas.fix_application import FixApplication


class NotVerifiableError(Exception):
    """Raised when a run isn't in a state where verification means anything."""


async def verify_design_analysis(
    db: AsyncSession,
    project: Project,
    analysis: DesignAnalysis,
    storage: StorageBackend,
    *,
    target_url: str | None = None,
) -> DesignAnalysis:
    """Re-measure the page and judge whether the applied patches worked.

    `target_url` overrides the project's own. That override is the whole
    reason this parameter exists: patches are applied to a local checkout,
    so a project whose target is a deployed site would otherwise be
    verified against a page that cannot have changed yet. Pointing it at a
    local dev server is the honest way to check a fix before deploying it.
    """
    if analysis.fix_application is None:
        raise NotVerifiableError("this run's patches haven't been applied yet")

    application = FixApplication.model_validate(analysis.fix_application)
    applied_titles = {fix.finding_title for fix in application.fixes if fix.applied}
    if not applied_titles:
        raise NotVerifiableError(
            "no patch on this run was actually written to a file, so there is nothing to verify"
        )

    # Everything the "before" side needs was recorded by the original run.
    # Missing any of it means the row predates a column rather than that
    # something went wrong now, so say which piece is absent.
    if analysis.production_screenshot_key is None or analysis.comparison_result is None:
        raise NotVerifiableError("this run has no stored production capture to compare against")
    if analysis.accessibility_report is None:
        raise NotVerifiableError("this run has no stored accessibility scan to compare against")
    if project.figma_screenshot_key is None:
        raise NotVerifiableError("this project has no Figma screenshot to compare against")

    state = VerificationState(
        project_id=project.id,
        figma_node=project.figma_data or {},
        figma_screenshot=storage.read(project.figma_screenshot_key),
        target_url=target_url or project.target_url,
        target_selector=project.target_selector,
        before_screenshot=storage.read(analysis.production_screenshot_key),
        before_comparison=ComparisonResult.model_validate(analysis.comparison_result),
        before_accessibility=AccessibilityReport.model_validate(analysis.accessibility_report),
        verified_findings=_findings_for(analysis, applied_titles),
    )
    final_state = await run_verification(state)

    assert final_state.verification is not None  # every path through the graph sets it
    assert final_state.after_screenshot is not None
    assert final_state.after_diff_screenshot is not None

    # New keys, not a rewrite of the originals: the before/after pair is
    # the deliverable, so overwriting the "before" would destroy the
    # comparison this whole step exists to make.
    attempt = uuid4()
    screenshot_key = f"design-analyses/{analysis.id}/verification/{attempt}-production.png"
    diff_key = f"design-analyses/{analysis.id}/verification/{attempt}-diff.png"
    storage.save(screenshot_key, final_state.after_screenshot)
    storage.save(diff_key, final_state.after_diff_screenshot)

    analysis.verification = final_state.verification.model_dump(mode="json")
    analysis.verification_screenshot_key = screenshot_key
    analysis.verification_diff_image_key = diff_key
    await db.commit()
    await db.refresh(analysis)
    return analysis


def _findings_for(analysis: DesignAnalysis, titles: set[str]) -> list[AggregatedFinding]:
    """The original findings behind the patches that were actually written.

    Re-read from the stored aggregation rather than reconstructed from the
    patches: the Verification Agent needs to know what the *problem* was,
    and a patch only records the change proposed for it.
    """
    if analysis.aggregated_findings is None:
        return []
    aggregated = AggregatedFindings.model_validate(analysis.aggregated_findings)
    return [finding for finding in aggregated.findings if finding.title in titles]
