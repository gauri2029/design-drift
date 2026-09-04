"""Shared state for the verification graph — the "did that fix actually
work?" pass that runs after a human approved patches and they were written
to the checkout (see app.services.design_analysis.apply_fix_review).

Separate from DesignQAState, and a separate graph, on purpose. The
diagnosis run ends at the human-review pause; verification happens later,
against a page that has since been rebuilt, and its inputs are what the
*previous* run recorded rather than what a node upstream just produced.
Threading it into DesignQAState would mean a state object where half the
fields are meaningless at any given moment, and a supervisor routing over
"has the human come back yet" — which is not a routing question a graph
can answer (see docs/architecture.md on why there's no checkpointer).

Same rules as DesignQAState otherwise: one typed model, explicit fields,
no free-form message passing (docs/principles.md #4).
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.agents.types import AggregatedFinding, VerificationResult
from app.integrations.axe.types import AccessibilityReport
from app.integrations.imaging.types import ComparisonResult


class VerificationState(BaseModel):
    project_id: UUID

    # --- what to capture, and what to compare it against ---
    figma_node: dict[str, Any]
    figma_screenshot: bytes
    # Not necessarily Project.target_url: a patch applied to a local
    # checkout doesn't change a deployed site until it's rebuilt, so the
    # caller may point verification at a dev server instead (see
    # app.services.verification).
    target_url: str
    target_selector: str | None = None

    # --- the "before" side, read off the original run ---
    before_screenshot: bytes
    before_comparison: ComparisonResult
    before_accessibility: AccessibilityReport
    # The findings whose patches were actually written to a file. Only
    # these are worth asking about — a rejected or skipped patch changed
    # nothing, so "is it fixed?" has a known answer.
    verified_findings: list[AggregatedFinding] = []

    # --- the "after" side, produced by the recapture node ---
    after_screenshot: bytes | None = None
    after_comparison: ComparisonResult | None = None
    after_diff_screenshot: bytes | None = None
    after_accessibility: AccessibilityReport | None = None

    # --- the Verification Agent's output ---
    verification: VerificationResult | None = None
