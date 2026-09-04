"""Verification Agent: did the applied fixes actually resolve what they
were meant to resolve? (see docs/architecture.md's runtime-agent table).

The measurements are already in — the recapture node re-ran the same
screenshot, axe-core scan, and pixel diff the original run used. What's
left is judgment, which is why this is the LLM half: axe can say the
`html-has-lang` rule stopped failing, but it can't say whether "the hero
button label reads 'Links' instead of 'Register Now'" is fixed. That
needs someone to look at the two images.

The deterministic delta is handed to the model as evidence rather than
being something it derives, and it's also kept in the result alongside the
verdicts, so a reader can check a verdict against the measurement instead
of taking it on trust.
"""

from typing import Any

from app.agents.recapture import accessibility_delta
from app.agents.types import (
    AccessibilityDelta,
    AggregatedFinding,
    VerificationJudgment,
    VerificationResult,
)
from app.graph.verification_state import VerificationState
from app.integrations.llm.client import generate_structured

SYSTEM_PROMPT = """\
You check whether code changes actually fixed the problems they were meant to fix.

A design QA run found problems on a web page. A human approved patches for some of \
them, the patches were written to the source, and the page was captured again. You are \
given, in this order: the Figma reference render (what the page should look like), the \
page BEFORE the fixes, and the page AFTER them. You also get the findings that were \
patched, and deterministic measurements taken from both captures.

For each finding you were given, decide whether it is resolved, unresolved, or unclear. \
Judge from the evidence in front of you, not from the fact that a patch was applied — a \
patch landing in a file is not proof it worked. If the accessibility measurements \
already answer a finding, say so and agree with them; they are exact and you are not \
being asked to second-guess them.

'unclear' is a real answer and you should use it. If a finding concerns part of the page \
you cannot see in these captures, or the difference is too small to call, say unclear \
rather than guessing.

Finally, look for regressions: anything that is worse after the change than before it. \
Expect to find none, and only report what you can actually see."""


async def verification_node(state: VerificationState) -> dict[str, Any]:
    # The recapture node only routes here when it left these unset — i.e.
    # when the page actually changed and there's something to judge.
    assert state.after_screenshot is not None
    assert state.after_comparison is not None
    assert state.after_accessibility is not None

    delta = accessibility_delta(state.before_accessibility, state.after_accessibility)

    judgment = await generate_structured(
        system=SYSTEM_PROMPT,
        text=_build_context_text(state, delta_lines(delta)),
        images=[state.figma_screenshot, state.before_screenshot, state.after_screenshot],
        output_format=VerificationJudgment,
    )

    return {
        "verification": VerificationResult(
            summary=judgment.summary,
            findings=judgment.findings,
            regressions=judgment.regressions,
            accessibility_delta=delta,
            mismatch_percentage_before=state.before_comparison.mismatch_percentage,
            mismatch_percentage_after=state.after_comparison.mismatch_percentage,
            production_changed=True,
        )
    }


def delta_lines(delta: AccessibilityDelta) -> str:
    return (
        f"- accessibility rules that stopped failing: {delta.resolved_rule_ids or 'none'}\n"
        f"- accessibility rules still failing: {delta.remaining_rule_ids or 'none'}\n"
        f"- accessibility rules that started failing: {delta.new_rule_ids or 'none'}"
    )


def _build_context_text(state: VerificationState, delta_text: str) -> str:
    assert state.after_comparison is not None

    findings = "\n".join(_finding_line(finding) for finding in state.verified_findings)
    return (
        f"Findings that were patched:\n{findings or '(none)'}\n\n"
        "Deterministic measurements:\n"
        f"- pixel mismatch vs. the Figma design before: "
        f"{state.before_comparison.mismatch_percentage:.2f}%\n"
        f"- pixel mismatch vs. the Figma design after: "
        f"{state.after_comparison.mismatch_percentage:.2f}%\n"
        f"{delta_text}"
    )


def _finding_line(finding: AggregatedFinding) -> str:
    return f"- [{finding.source}/{finding.priority}] {finding.title}: {finding.detail}"
