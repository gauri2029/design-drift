"""Fix Agent: propose a code patch for each located finding (see
docs/architecture.md's runtime-agent table — "propose a code patch (never
applies/publishes)").

It proposes text and nothing else. Nothing here writes to the checkout,
stages a commit, or touches a remote — docs/principles.md #5 puts every
consequential action behind a human, and the repository owner does all Git
operations by hand. `app.tools.repo_search` is read-only for the same
reason.

Runs only after Code Analysis, and only on findings it actually located: a
patch needs a file and a line range to change, so a `no_match` finding has
nothing to act on. That keeps this node's input concrete — real code at
real lines — rather than asking a model to invent a change from prose.

One deterministic check afterwards. The model's patch names the code it
intends to replace; whether that code is really in the file is a fact, so
it's verified in Python instead of trusted (docs/principles.md #2). A
patch that fails is kept and flagged rather than dropped — a reviewer
should see both the proposal and that it doesn't apply, which is also the
clearest signal the model drifted from the evidence.
"""

from typing import Any

from app.agents.types import (
    AggregatedFinding,
    FindingLocation,
    FixProposal,
    FixResult,
    ProposedFix,
    VerifiedFix,
)
from app.graph.state import DesignQAState
from app.integrations.llm.client import generate_structured
from app.tools.repo_search import load_source_corpus

SYSTEM_PROMPT = """\
You propose minimal source-code patches that fix design-QA findings about a web page.

For each finding you are given the exact file and line range responsible, and the code at \
that location with real line numbers.

Propose the smallest change that fixes the finding. Copy `original_code` character-for-character \
from the code you were shown, without the line-number prefixes — it is checked against the real \
file, so an approximation will be rejected. Preserve the surrounding indentation.

Set no_fix when you cannot propose a safe, self-contained patch: when the correct content isn't \
in the evidence (for example, replacement copy that only exists in a design), or when the fix is \
a structural change reaching well beyond the lines you were shown. A patch that guesses at \
content is worse than saying so — a human will have to undo it.

You are proposing only. Nothing you return is applied automatically; a human reviews every \
change."""


async def fix_node(state: DesignQAState) -> dict[str, Any]:
    # Both guaranteed by route_after_supervisor, which only sends us here
    # once Code Analysis located something in a resolved checkout.
    assert state.code_analysis is not None
    assert state.source_root is not None

    located = [location for location in state.code_analysis.locations if not location.no_match]
    corpus = load_source_corpus(state.source_root)
    findings = {finding.title: finding for finding in _findings(state)}

    proposal = await generate_structured(
        system=SYSTEM_PROMPT,
        text=_build_context_text(located, findings, corpus),
        images=[],
        output_format=FixProposal,
    )

    return {
        "fix_proposal": FixResult(
            summary=proposal.summary,
            fixes=[_verify(fix, corpus) for fix in proposal.fixes],
        )
    }


def _findings(state: DesignQAState) -> list[AggregatedFinding]:
    return state.aggregated_findings.findings if state.aggregated_findings else []


def _verify(fix: ProposedFix, corpus: dict[str, list[str]]) -> VerifiedFix:
    """Check the patch's `original_code` really is in the file.

    Compared with whitespace normalized per line: the model reproduces the
    code from a numbered snippet, so trailing spaces and the exact indent
    are easy to lose in ways that don't change what's being replaced. What
    matters is that the *code* exists, not that the copy is byte-perfect.
    """
    found = False
    if not fix.no_fix and fix.patch is not None:
        lines = corpus.get(fix.patch.file_path)
        if lines is not None:
            haystack = "\n".join(line.strip() for line in lines)
            needle = "\n".join(
                line.strip() for line in fix.patch.original_code.splitlines() if line.strip()
            )
            found = bool(needle) and needle in haystack

    return VerifiedFix(**fix.model_dump(), original_code_found=found)


def _build_context_text(
    located: list[FindingLocation],
    findings: dict[str, AggregatedFinding],
    corpus: dict[str, list[str]],
) -> str:
    if not located:
        return "No findings were located in the source, so there is nothing to patch."

    blocks: list[str] = []
    for index, location in enumerate(located, 1):
        assert location.location is not None  # no_match filtered out by the caller
        patch_target = location.location
        finding = findings.get(location.finding_title)

        detail = finding.detail if finding else location.explanation
        code = _numbered_code(
            corpus, patch_target.file_path, patch_target.line_start, patch_target.line_end
        )

        blocks.append(
            f"### Finding {index}: {location.finding_title}\n"
            f"{detail}\n\n"
            f"Located at {patch_target.file_path} lines "
            f"{patch_target.line_start}-{patch_target.line_end}:\n"
            f"```\n{code}\n```"
        )

    return "\n\n---\n\n".join(blocks)


# Context around the located range, so a patch can extend slightly beyond
# the exact lines Code Analysis pinned (closing a tag, wrapping an element)
# without the model having to guess what surrounds them.
CONTEXT_LINES = 8


def _numbered_code(corpus: dict[str, list[str]], path: str, line_start: int, line_end: int) -> str:
    lines = corpus.get(path)
    if lines is None:
        return "(file not found in the checkout)"

    start = max(1, line_start - CONTEXT_LINES)
    end = min(len(lines), line_end + CONTEXT_LINES)
    return "\n".join(f"{number}: {lines[number - 1]}" for number in range(start, end + 1))
