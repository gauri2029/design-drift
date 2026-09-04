from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.agents.types import (
    AccessibilityInterpretation,
    AggregatedFindings,
    CodeAnalysisResult,
    DesignAnalysisResult,
    FixResult,
    VerificationResult,
)
from app.integrations.axe.types import AccessibilityReport
from app.integrations.imaging.types import ComparisonResult
from app.integrations.llm.types import VisualReviewResult
from app.schemas.fix_application import FixApplication
from app.schemas.fix_review import FixReview


class DesignAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    model: str
    result: DesignAnalysisResult
    production_screenshot_key: str | None
    comparison_result: ComparisonResult | None
    diff_image_key: str | None
    visual_comparison: VisualReviewResult | None
    accessibility_report: AccessibilityReport | None
    accessibility_interpretation: AccessibilityInterpretation | None
    aggregated_findings: AggregatedFindings | None
    # Null when Code Analysis didn't run — see app.agents.supervisor's fork.
    code_analysis: CodeAnalysisResult | None
    # Null when Code Analysis located nothing to patch.
    fix_proposal: FixResult | None
    # Null until a human reviews the proposals — see app.schemas.fix_review.
    fix_review: FixReview | None
    # Null until the approved patches are applied — see
    # app.schemas.fix_application.
    fix_application: FixApplication | None
    # Null until the applied patches are verified — a second graph run
    # against the rebuilt page (see app.services.verification).
    verification: VerificationResult | None
    verification_screenshot_key: str | None
    verification_diff_image_key: str | None
    created_at: datetime
