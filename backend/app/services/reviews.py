"""Multimodal visual-reasoning review: the first LLM-backed step in the
pipeline (docs/principles.md #2 — everything upstream is deterministic;
this is where judgment enters).

Plain async service, no LangGraph/agent involved yet — same rationale as
app.services.scans (see its module docstring). This is the deterministic
"assemble inputs, call the LLM once, persist the result" step a future
Visual Comparison Agent will wrap as a tool. Unlike create_scan(), this is
never triggered automatically — running it costs real money per call, so
it's an explicit action the frontend gates behind a button, not something
that happens on every scan.
"""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.integrations.llm.client import generate_structured
from app.integrations.llm.types import VisualReviewResult
from app.integrations.storage.base import StorageBackend
from app.models.project import Project
from app.models.review import Review
from app.models.scan import Scan

SYSTEM_PROMPT = """\
You review a web page's visual implementation against its Figma design.

You are given three images, always in this order: the Figma reference render \
(expected), a screenshot of the live production page (actual), and a pixel-diff \
visualization highlighting where they differ. You are also given deterministic \
measurements: a raw pixel-mismatch percentage from image diffing, and accessibility \
violations from axe-core.

The pixel-mismatch percentage alone cannot tell real design drift apart from \
inconsequential differences — antialiasing, font rendering, or (when the sizes \
genuinely differ) the padding introduced by comparing a small element against a \
larger canvas. Your job is that judgment call: look at the actual images and decide \
whether the difference is a real, material design problem, and if so, describe \
specifically what's wrong.

Ground every finding in what you can actually see in the images. You have no access \
to source code, so don't speculate about implementation causes — describe what's \
wrong visually and, if you can tell, which part of the UI is responsible."""


async def create_review(
    db: AsyncSession, project: Project, scan: Scan, storage: StorageBackend
) -> Review:
    # project.figma_screenshot_key and scan's screenshot/diff keys are all
    # guaranteed non-null by the time a Scan exists (create_scan requires
    # project.figma_screenshot_key up front, and always writes its own).
    figma_png = storage.read(project.figma_screenshot_key)  # type: ignore[arg-type]
    production_png = storage.read(scan.production_screenshot_key)
    diff_png = storage.read(scan.diff_image_key)

    result = await generate_structured(
        system=SYSTEM_PROMPT,
        text=_build_context_text(project, scan),
        images=[figma_png, production_png, diff_png],
        output_format=VisualReviewResult,
    )

    settings = get_settings()
    review = Review(
        id=uuid4(),
        scan_id=scan.id,
        model=settings.llm_model,
        result=result.model_dump(mode="json"),
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


async def list_reviews(db: AsyncSession, scan_id: UUID) -> list[Review]:
    result = await db.execute(
        select(Review).where(Review.scan_id == scan_id).order_by(Review.created_at.desc())
    )
    return list(result.scalars().all())


def _build_context_text(project: Project, scan: Scan) -> str:
    node: dict[str, Any] = project.figma_data or {}
    comparison: dict[str, Any] = scan.comparison_result
    accessibility: dict[str, Any] = scan.accessibility_report
    violation_ids = [v["id"] for v in accessibility.get("violations", [])]

    return (
        f"Figma node: name={node.get('name')!r}, type={node.get('type')!r}\n"
        f"Deterministic pixel diff: {comparison['mismatch_percentage']:.2f}% mismatch, "
        f"dimensions_match={comparison['dimensions_match']}, "
        f"expected_dimensions={comparison['expected_dimensions']}, "
        f"actual_dimensions={comparison['actual_dimensions']}\n"
        f"Accessibility (axe-core, deterministic): "
        f"{accessibility.get('violation_count', 0)} violation(s): {violation_ids}\n\n"
        "Images provided, in order: (1) Figma reference render — the expected design, "
        "(2) production screenshot — what the live app actually shows, "
        "(3) pixel-diff visualization — differing pixels highlighted."
    )
