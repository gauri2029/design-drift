"""Design QA workflow orchestration: assemble inputs from a project (its
stored Figma data, its target app), run the LangGraph workflow, persist
the result.

Unlike app.services.projects/scans (plain service functions calling
integrations directly, per those modules' docstrings), this is the first
place an actual LangGraph graph runs — see app.graph.workflow for the
graph itself and docs/architecture.md for where this fits in the target
multi-agent workflow. The graph currently runs Design Analysis, then
Production Analysis, then Visual Comparison, then Accessibility, then the
findings aggregation, then conditionally Code Analysis (see
app.graph.state.DesignQAState); this function's name/table stay
"design_analysis" rather than being renamed each time the graph gains a
node, same as Scan's name didn't change when breakpoints were added to it.

Like app.services.reviews, this is never triggered automatically — it
costs real money and launches a real browser per call, so it's an
explicit action the frontend gates behind a button.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.types import Patch
from app.core.config import get_settings
from app.graph.state import DesignQAState
from app.graph.workflow import run_design_qa
from app.integrations.storage.base import StorageBackend
from app.models.design_analysis import DesignAnalysis
from app.models.project import Project
from app.schemas.fix_application import AppliedFix, FixApplication
from app.schemas.fix_review import FixDecision, FixDecisionItem, FixReview
from app.tools.apply_patch import apply_patches
from app.tools.repo_search import resolve_source_root


class ProjectNotAnalyzableError(Exception):
    """Raised when a project has no usable Figma data yet to analyze."""


class FixApplicationError(Exception):
    """Raised when approved patches can't be applied to the checkout.

    Like FixReviewError, every case is about the state of this run or its
    project — not reviewed, already applied, no checkout configured — so
    the router surfaces it as a 409.
    """


class FixReviewError(Exception):
    """Raised when a review decision doesn't fit what the run proposed.

    Every case is about the state of *this* run (no proposals to review, a
    finding it never proposed a fix for, a patch that doesn't apply), not
    about the request being malformed — hence one exception, surfaced as a
    409 by the router.
    """


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
        # Resolved (and containment-checked) here rather than inside the
        # Code Analysis node, so a bad path fails before any paid LLM call
        # or browser launch happens — and so nodes never handle a raw
        # user-supplied path themselves.
        source_root=_resolve_source_root(project),
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
    assert final_state.aggregated_findings is not None

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
        aggregated_findings=final_state.aggregated_findings.model_dump(mode="json"),
        # Not asserted non-None like the fields above: Code Analysis and the
        # Fix Agent are conditional, so None here is a normal outcome (no
        # problems found, no source checkout, or nothing located to patch)
        # rather than a missing artifact.
        code_analysis=(
            final_state.code_analysis.model_dump(mode="json")
            if final_state.code_analysis is not None
            else None
        ),
        fix_proposal=(
            final_state.fix_proposal.model_dump(mode="json")
            if final_state.fix_proposal is not None
            else None
        ),
    )
    db.add(design_analysis)
    await db.commit()
    await db.refresh(design_analysis)
    return design_analysis


async def review_fix_proposal(
    db: AsyncSession, analysis: DesignAnalysis, decisions: list[FixDecisionItem]
) -> DesignAnalysis:
    """Record a human's approve/reject decision on the proposed patches.

    This is the pause in docs/architecture.md's flow. It only *records* the
    decision — nothing here writes to a checkout, stages a commit, or
    touches a remote (docs/principles.md #5). Approving is a sign-off, and
    the input the later apply/verify slice will read.

    Re-reviewing replaces the previous review rather than appending to it.
    """
    proposal = analysis.fix_proposal
    if proposal is None:
        raise FixReviewError("this run proposed no fixes, so there is nothing to review")

    reviewable = _reviewable_fixes(proposal)
    seen: set[str] = set()
    for item in decisions:
        if item.finding_title in seen:
            raise FixReviewError(f"duplicate decision for {item.finding_title!r}")
        seen.add(item.finding_title)
        if item.finding_title not in reviewable:
            raise FixReviewError(f"this run proposed no patch for {item.finding_title!r}")
        # Approving a patch whose original_code isn't in the file would be
        # signing off on something that cannot be applied. That's a fact we
        # already checked (app.agents.fix), so refuse it here rather than
        # letting it fail later. Rejecting one is fine — and expected.
        if item.decision is FixDecision.APPROVED and not reviewable[item.finding_title]:
            raise FixReviewError(
                f"{item.finding_title!r} cannot be approved: its original code no longer "
                "matches the file, so the patch does not apply"
            )

    analysis.fix_review = FixReview(decisions=decisions, reviewed_at=datetime.now(UTC)).model_dump(
        mode="json"
    )
    await db.commit()
    await db.refresh(analysis)
    return analysis


def _reviewable_fixes(proposal: dict[str, object]) -> dict[str, bool]:
    """Title -> whether its patch still applies, for fixes that have a patch.

    Read off the stored JSONB rather than re-validating it into a
    FixResult: this only needs two fields, and a run persisted before a
    later contract change should still be reviewable.
    """
    fixes = proposal.get("fixes")
    if not isinstance(fixes, list):
        return {}
    return {
        fix["finding_title"]: bool(fix.get("original_code_found"))
        for fix in fixes
        if isinstance(fix, dict)
        and isinstance(fix.get("finding_title"), str)
        and not fix.get("no_fix")
        and fix.get("patch") is not None
    }


async def apply_fix_review(
    db: AsyncSession, project: Project, analysis: DesignAnalysis
) -> DesignAnalysis:
    """Write this run's *approved* patches into the project's checkout.

    The only write path in the application, and it is deliberately narrow:
    approved patches only, files only inside the project's configured
    source root, and each patch re-checked against the file as it is now
    (app.tools.apply_patch). Nothing here runs git — no staging, no
    commit, no push (docs/principles.md #5). The user's own version
    control is what makes this safe to undo, so it stays theirs to drive.

    Applied once. A run records what a single act of applying did; running
    it again would be a second event against a checkout that has already
    changed, and re-deriving it from the same stale snippets is not what
    anyone wants — re-run the workflow instead.
    """
    if analysis.fix_application is not None:
        raise FixApplicationError("this run's approved patches have already been applied")

    approved = _approved_titles(analysis.fix_review)
    if not approved:
        raise FixApplicationError("no patches on this run have been approved yet")

    source_root = _resolve_source_root(project)
    if source_root is None:
        raise FixApplicationError(
            "this project has no source checkout configured, so there is nothing to apply to"
        )

    patches = _approved_patches(analysis.fix_proposal, approved)
    outcomes = apply_patches(source_root, patches)

    analysis.fix_application = FixApplication(
        applied_at=datetime.now(UTC),
        fixes=[
            AppliedFix(
                finding_title=title,
                file_path=patch.file_path,
                applied=outcomes[title].applied,
                reason=outcomes[title].reason,
            )
            for title, patch in patches
        ],
    ).model_dump(mode="json")
    await db.commit()
    await db.refresh(analysis)
    return analysis


def _approved_titles(fix_review: dict[str, object] | None) -> set[str]:
    if fix_review is None:
        return set()
    decisions = fix_review.get("decisions")
    if not isinstance(decisions, list):
        return set()
    return {
        decision["finding_title"]
        for decision in decisions
        if isinstance(decision, dict) and decision.get("decision") == FixDecision.APPROVED.value
    }


def _approved_patches(
    fix_proposal: dict[str, object] | None, approved: set[str]
) -> list[tuple[str, Patch]]:
    """The stored patches for approved findings, in proposal order.

    Validated into a Patch here rather than passed as raw JSONB: this is
    the point where stored data becomes an instruction to write to disk,
    so it gets checked against the contract first.
    """
    if fix_proposal is None:
        return []
    fixes = fix_proposal.get("fixes")
    if not isinstance(fixes, list):
        return []
    patches: list[tuple[str, Patch]] = []
    for fix in fixes:
        if not isinstance(fix, dict) or fix.get("finding_title") not in approved:
            continue
        if fix.get("no_fix") or fix.get("patch") is None:
            continue
        patches.append((str(fix["finding_title"]), Patch.model_validate(fix["patch"])))
    return patches


def _resolve_source_root(project: Project) -> Path | None:
    """None when the project has no source checkout configured.

    A configured-but-unusable path is a different case and raises: it's a
    misconfiguration the user should hear about, not something to silently
    treat as "no source available" and skip past.
    """
    if not project.source_path:
        return None
    return resolve_source_root(project.source_path)


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
