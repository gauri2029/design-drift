"""Structured-output contract for the Design Analysis Agent (see
docs/architecture.md's runtime-agent table).

Distinct from app.integrations.llm.types.VisualReviewResult: that's the
Visual Comparison Agent's job (Figma vs. production, judging drift). This
agent only ever sees the Figma side — it interprets structure and intent
before any production capture exists, so a later Visual Comparison pass
knows what to compare against, and a later Code Analysis / Fix Agent pass
knows what's risky to get wrong.
"""

from pydantic import BaseModel, Field


class DesignComponent(BaseModel):
    name: str = Field(
        description="Short name for this component/region, e.g. 'primary CTA button'."
    )
    role: str = Field(description="This component's apparent purpose within the design.")
    notable_styling: str = Field(
        description=(
            "Key style choices worth preserving in an implementation: colors, spacing, "
            "typography, alignment, etc."
        )
    )


class DesignAnalysisResult(BaseModel):
    layout_summary: str = Field(
        description="Plain-language summary of the overall layout and structure."
    )
    design_intent: str = Field(
        description=(
            "What this design is trying to achieve for the user — its apparent purpose and "
            "priorities."
        )
    )
    key_components: list[DesignComponent] = Field(
        default_factory=list,
        description=(
            "The most important distinct components/regions in this design, ordered by "
            "visual prominence."
        ),
    )
    implementation_risks: list[str] = Field(
        default_factory=list,
        description=(
            "Aspects of this design that are easy to get subtly wrong when implementing in "
            "code — precise spacing, a non-obvious layout technique, responsive behavior that "
            "isn't visible in a single static render, and so on. Flagged so a later comparison "
            "pass knows what to scrutinize most closely."
        ),
    )
