"""Code Analysis Agent: locate the exact source responsible for each
finding (see docs/architecture.md's runtime-agent table).

The first node on the *remediation* side of the workflow — everything
before it inspects the running app, this one starts reasoning about the
code behind it. Also the first node that only runs conditionally: the
Supervisor routes here only when `aggregated_findings.problems_found` is
True and the project actually has a source checkout configured, which is
what makes docs/architecture.md's `route: problems found?` fork a real
fork rather than two paths to the same place.

Retrieve, then reason — the split docs/principles.md #2 asks for:

1. Deterministic anchors come out of what the inspection agents already
   observed (app.tools.anchors) — ids, class names, accessible names and
   visible text, mostly from the real DOM axe-core reports per violation.
2. A deterministic content search ranks files by how much of that evidence
   they contain, and returns snippets with real line numbers
   (app.tools.repo_search).
3. Only then does the LLM judge which candidate is actually the cause.

The earlier version of this node skipped 1 and 2 and handed the model a
bare list of file paths. That reads well in a tidy repo with a
`Button.tsx`, and degrades badly in a real one — utility CSS, shared
stylesheets and generated markup leave nothing in a filename to reason
from. Narrowing deterministically first is both cheaper and more honest:
the model now sees the actual lines it's judging.

Not a tool-use loop. The model can't request more files; it sees the
candidates the search chose and nothing else. That keeps every node in
this graph on the same single structured call, and keeps the set of files
that can reach an LLM API decided by our code rather than by the model —
which matters given those files come from a user-configured path (see
app.tools.repo_search.resolve_source_root). A genuine search->read->refine
loop would locate more, and is the next step up.
"""

from typing import Any

from app.agents.types import AggregatedFinding, CodeAnalysisResult, FindingSource
from app.graph.state import DesignQAState
from app.integrations.llm.client import generate_structured
from app.tools.anchors import Anchor, extract_anchors
from app.tools.repo_search import (
    CandidateMatch,
    load_source_corpus,
    search_corpus,
)

SYSTEM_PROMPT = """\
You locate the exact source code responsible for design-QA findings about a web page.

For each finding you are given candidate code snippets, pulled from the project's source \
by searching for concrete evidence observed on the live page — element ids, class names, \
accessible names, and visible text. Every snippet is labelled with its file path and real \
line numbers.

Work only from those snippets. Do not name a file that wasn't offered as a candidate, and \
do not guess at line numbers you can't see.

Pick the single most likely location per finding, and quote the exact lines that justify \
it. Where the snippets don't actually show something that would cause the finding, set \
no_match — a developer sent to the wrong file loses more time than one told we couldn't \
find it. Candidates are ranked by a keyword search that has no understanding of the code, \
so a high-ranked candidate can still be irrelevant."""


async def code_analysis_node(state: DesignQAState) -> dict[str, Any]:
    # Both guaranteed by route_after_supervisor, which only sends us here
    # once findings exist and a source root resolved.
    assert state.aggregated_findings is not None
    assert state.source_root is not None

    # Read the checkout once; each finding then searches it separately, so
    # one finding's evidence can't pull in another's unrelated matches.
    corpus = load_source_corpus(state.source_root)

    searched = [
        (finding, search_corpus(corpus, _anchors_for(finding, state)))
        for finding in state.aggregated_findings.findings
    ]

    result = await generate_structured(
        system=SYSTEM_PROMPT,
        text=_build_context_text(searched),
        images=[],
        output_format=CodeAnalysisResult,
    )
    return {"code_analysis": result}


def _anchors_for(finding: AggregatedFinding, state: DesignQAState) -> list[Anchor]:
    """Anchors for one finding, from the best evidence available for it.

    Accessibility findings carry a hard link to real DOM: their title *is*
    the axe violation id (see app.agents.aggregate_findings), so evidence
    narrows to the elements axe flagged for that specific rule.

    Visual findings have no such link — they're the Visual Comparison
    Agent's prose about two images — so what they name is looked up in the
    page's DOM snapshot instead: a finding about a button the model called
    "Links" resolves to that element's real id and classes, which is the
    same kind of evidence axe gives an accessibility finding. When a
    visual finding names nothing that exists on the page, that legitimately
    yields no anchors and the model is told to answer no_match, rather than
    keywords being guessed out of prose.
    """
    is_accessibility = finding.source is FindingSource.ACCESSIBILITY
    return extract_anchors(
        texts=[finding.title, finding.detail, finding.likely_area or ""],
        accessibility_report=state.accessibility_report,
        violation_ids=[finding.title] if is_accessibility else [],
        target_selector=state.target_selector,
        dom_snapshot=state.production_dom,
    )


def _build_context_text(
    searched: list[tuple[AggregatedFinding, list[CandidateMatch]]],
) -> str:
    if not searched:
        return "No findings were produced."

    blocks: list[str] = []
    for index, (finding, candidates) in enumerate(searched, 1):
        header = (
            f"### Finding {index}: {finding.title}\n"
            f"priority={finding.priority.value}, from={finding.source.value}\n"
            f"{finding.detail}"
        )
        if finding.likely_area:
            header += f"\nReported UI area: {finding.likely_area}"

        if candidates:
            body = "\n\n".join(
                f"Candidate {rank} — {candidate.path} "
                f"(lines {candidate.line_start}-{candidate.line_end}, "
                f"matched: {', '.join(candidate.matched_anchors)})\n"
                f"```\n{candidate.snippet}\n```"
                for rank, candidate in enumerate(candidates, 1)
            )
        else:
            body = (
                "No candidates: the search found no file containing evidence for this "
                "finding. Set no_match unless you have some other basis."
            )
        blocks.append(f"{header}\n\n{body}")

    return "\n\n---\n\n".join(blocks)
