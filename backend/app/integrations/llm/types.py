"""Structured-output schema for the multimodal visual-reasoning review.

This is the contract Phase 3's Code Analysis Agent will consume (see
docs/architecture.md's runtime-agent table) — kept deliberately small and
concrete (enums, short free-text fields) rather than open-ended, since it's
meant to be a stable interface between phases. Field descriptions matter
here: client.messages.parse() derives the JSON schema Claude is constrained
to from this model, and the description text is part of what the model
sees.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class FindingCategory(StrEnum):
    LAYOUT = "layout"
    SPACING = "spacing"
    TYPOGRAPHY = "typography"
    COLOR = "color"
    RESPONSIVE = "responsive"
    ACCESSIBILITY = "accessibility"
    COMPONENT_STRUCTURE = "component_structure"
    OTHER = "other"


class FindingSeverity(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    COSMETIC = "cosmetic"


class DesignFinding(BaseModel):
    category: FindingCategory = Field(description="Which aspect of the design this is about.")
    severity: FindingSeverity = Field(
        description=(
            "How much this affects the user-facing product: critical (broken/unusable), "
            "major (clearly wrong, noticeable), minor (noticeable on close inspection), "
            "cosmetic (technically off but inconsequential)."
        )
    )
    title: str = Field(description="One short sentence naming the problem.")
    description: str = Field(
        description=(
            "What is wrong, comparing what the Figma design shows against what the production "
            "screenshot actually shows. Be specific: name the element, the expected value, and "
            "the actual value where you can tell them apart."
        )
    )
    evidence: str = Field(
        description=(
            "What in the images supports this finding — e.g. 'the button in the production "
            "screenshot is visibly narrower than in the Figma reference' or 'the diff image "
            "shows a solid red region across the header'."
        )
    )
    likely_area: str | None = Field(
        default=None,
        description=(
            "A plain-language description of the UI area responsible (e.g. 'the primary "
            "call-to-action button' or 'the page header'). This is NOT a file path — no source "
            "code is available at this stage; a later phase maps this to actual files."
        ),
    )


class VisualReviewResult(BaseModel):
    material_drift_detected: bool = Field(
        description=(
            "Your overall judgment: does this represent a real, material design problem worth "
            "a human's attention, as opposed to noise (antialiasing, font-rendering "
            "differences, or — when the sizes genuinely differ — the padding introduced by "
            "comparing a small element against a larger canvas)?"
        )
    )
    summary: str = Field(description="One-paragraph, plain-language summary of the review.")
    findings: list[DesignFinding] = Field(
        default_factory=list,
        description=(
            "Individual findings, ordered most severe first. Empty if there's nothing worth "
            "flagging beyond noise."
        ),
    )
