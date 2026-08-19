"""Aggregate findings: merge every agent's findings into one triaged list
(see docs/architecture.md's flow, `aggregate findings`).

Fully deterministic — no LLM call, and not really an "agent" despite
living in this package alongside them (as with production_analysis, this
package holds graph *nodes*, deterministic or not). Every judgment call
this depends on has already been made: the Visual Comparison Agent decided
which visual differences are material, and the Accessibility Agent decided
which violations are urgent. Re-asking a model to merge two lists it
already produced would be exactly the "fake AI" docs/principles.md #2
rules out — merging and sorting are things Python does correctly and for
free.

What this exists for: the two agents report in different shapes and on
different scales, so anything downstream (a Code Analysis pass, the
frontend) would otherwise have to know both. This flattens them to one
shape with one ordering, without discarding either agent's raw output —
that stays on the state, and in its own persisted column.
"""

from typing import Any

from app.agents.types import (
    AggregatedFinding,
    AggregatedFindings,
    FindingPriority,
    FindingSource,
)
from app.graph.state import DesignQAState
from app.integrations.llm.types import DesignFinding, FindingSeverity

# Visual severity measures how wrong something looks; FindingPriority
# measures how urgently to act. Both "critical" (broken/unusable) and
# "major" (clearly wrong, noticeable) warrant acting now, so both map to
# HIGH — see FindingPriority's docstring on why that's acceptable here.
_VISUAL_SEVERITY_TO_PRIORITY = {
    FindingSeverity.CRITICAL: FindingPriority.HIGH,
    FindingSeverity.MAJOR: FindingPriority.HIGH,
    FindingSeverity.MINOR: FindingPriority.MEDIUM,
    FindingSeverity.COSMETIC: FindingPriority.LOW,
}

_PRIORITY_ORDER = {
    FindingPriority.HIGH: 0,
    FindingPriority.MEDIUM: 1,
    FindingPriority.LOW: 2,
}


def aggregate_findings_node(state: DesignQAState) -> dict[str, Any]:
    # Both guaranteed set by the time the supervisor routes here, but read
    # defensively rather than asserting: an empty merge is a meaningful,
    # representable answer ("nothing found"), unlike the None-checks in
    # app.services.design_analysis where a missing artifact is a real bug.
    findings: list[AggregatedFinding] = []

    visual = state.visual_comparison
    if visual is not None:
        findings.extend(_from_visual(finding) for finding in visual.findings)

    accessibility = state.accessibility_interpretation
    if accessibility is not None:
        findings.extend(
            AggregatedFinding(
                source=FindingSource.ACCESSIBILITY,
                priority=FindingPriority(issue.priority.value),
                original_severity=issue.priority.value,
                title=issue.violation_id,
                detail=issue.user_impact,
            )
            for issue in accessibility.most_important_issues
        )

    # Stable sort, so findings of equal priority keep the order the agent
    # that produced them chose (both agents order their own output
    # most-severe first).
    findings.sort(key=lambda finding: _PRIORITY_ORDER[finding.priority])

    # `material_drift_detected` is the Visual Comparison Agent's overall
    # verdict, which can be True even when it itemized nothing — so it
    # counts as a problem in its own right, not just via `findings`.
    problems_found = bool(findings) or bool(visual is not None and visual.material_drift_detected)

    return {
        "aggregated_findings": AggregatedFindings(
            problems_found=problems_found, findings=findings
        )
    }


def _from_visual(finding: DesignFinding) -> AggregatedFinding:
    return AggregatedFinding(
        source=FindingSource.VISUAL_COMPARISON,
        priority=_VISUAL_SEVERITY_TO_PRIORITY[finding.severity],
        original_severity=finding.severity.value,
        title=finding.title,
        detail=finding.description,
        likely_area=finding.likely_area,
    )
