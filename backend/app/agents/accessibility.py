"""Accessibility Agent: deterministic axe-core violations, then an LLM
triage pass over them (see docs/architecture.md's runtime-agent table:
"axe-core, LLM (interpretation only)"). Same shape as Visual Comparison —
one deterministic tool call followed by one LLM judgment call in a single
node, since the judgment needs the scan's own output first.

Unlike the other two LLM-backed nodes, this one is text-only: axe-core
already tells you exactly which DOM elements violate which rules, so
there's no ambiguity an image would help resolve. The judgment call is
prioritization — which violations most deserve a human's attention first
— not "what happened," which axe-core already answered deterministically.

Skips the LLM call entirely when there are no violations: the answer is
trivially "nothing to interpret," not worth a paid call.
"""

from typing import Any

from app.agents.types import AccessibilityInterpretation
from app.graph.state import DesignQAState
from app.integrations.axe.scan import run_accessibility_scan
from app.integrations.axe.types import AccessibilityReport
from app.integrations.llm.client import generate_structured

SYSTEM_PROMPT = """\
You triage a web page's accessibility violations, found deterministically by axe-core.

You are given a list of violations, each with its rule id, axe's own severity rating \
("impact"), a description, and the affected DOM elements. axe-core already told you \
*what's* wrong; your job is judgment: which of these most deserve a human's attention \
first, and why — in terms of how a real user would actually be blocked or hindered, not \
a restatement of the rule text.

You don't need to cover every violation — just the ones genuinely worth calling out. \
Ground every issue you raise in the violation data you were given."""


async def accessibility_node(state: DesignQAState) -> dict[str, Any]:
    report = await run_accessibility_scan(state.target_url, selector=state.target_selector)

    if report.violation_count == 0:
        return {
            "accessibility_report": report,
            "accessibility_interpretation": AccessibilityInterpretation(
                summary="No accessibility violations detected.", most_important_issues=[]
            ),
        }

    interpretation = await generate_structured(
        system=SYSTEM_PROMPT,
        text=_build_context_text(report),
        images=[],
        output_format=AccessibilityInterpretation,
    )
    return {"accessibility_report": report, "accessibility_interpretation": interpretation}


def _build_context_text(report: AccessibilityReport) -> str:
    violations = "\n".join(
        f"- id={v.id!r}, impact={v.impact!r}, description={v.description!r}, "
        f"elements_affected={len(v.nodes)}"
        for v in report.violations
    )
    return f"{report.violation_count} axe-core violation(s):\n{violations}"
