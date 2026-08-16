from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.integrations.axe.types import AccessibilityReport
from app.integrations.imaging.types import ComparisonResult
from app.integrations.playwright.breakpoints import STANDARD_BREAKPOINTS


class ScanCreate(BaseModel):
    viewport_width: int = 1280
    viewport_height: int = 800
    # Name of a standard breakpoint (see STANDARD_BREAKPOINTS) — overrides
    # viewport_width/viewport_height when set.
    breakpoint: str | None = None

    @model_validator(mode="after")
    def _validate_breakpoint(self) -> "ScanCreate":
        if self.breakpoint is not None and self.breakpoint not in STANDARD_BREAKPOINTS:
            known = ", ".join(sorted(STANDARD_BREAKPOINTS))
            raise ValueError(f"unknown breakpoint {self.breakpoint!r}; expected one of {known}")
        return self


class ScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    viewport_width: int
    viewport_height: int
    breakpoint: str | None
    production_screenshot_key: str
    diff_image_key: str
    # Raw pixel-diff result (see ComparisonResult's docstring) — not a
    # design fidelity score.
    comparison_result: ComparisonResult
    # Deterministic axe-core violations against the same production capture.
    accessibility_report: AccessibilityReport
    created_at: datetime
