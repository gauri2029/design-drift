"""Typed models for axe-core's violation output.

Mirrors axe-core's own JSON shape (camelCase alias generator, matching the
pattern in app.integrations.figma.types) so callers get validated Pydantic
models rather than raw dicts.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class AxeModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class AxeNode(AxeModel):
    target: list[str] = []
    html: str | None = None
    failure_summary: str | None = None


class AxeViolation(AxeModel):
    id: str
    impact: str | None = None  # "minor" | "moderate" | "serious" | "critical" | None
    description: str
    help: str
    help_url: str
    tags: list[str] = []
    nodes: list[AxeNode] = []


class AccessibilityReport(BaseModel):
    violations: list[AxeViolation]
    violation_count: int
