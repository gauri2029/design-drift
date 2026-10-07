"""Run the Code Analysis retrieval path over eval cases and score it.

Calls the *same* functions the agent calls — extract_anchors, search_corpus,
and the real system prompt via generate_structured — rather than a copy.
A harness that reimplements the thing it measures measures the copy, and
then silently stops tracking the code after the first divergence.

Two modes, because they answer different questions:

- `--search-only` scores the deterministic half by its top-ranked
  candidate. No LLM, no API key, no cost, so it runs in CI and on every
  change to anchors or ranking.
- the default scores the whole path, LLM included. Costs real calls, so
  it's run deliberately.

Neither number is "the" score, and the gap between them is the interesting
part. Some cases the search cannot be expected to win alone — asked which
of two files causes a contrast bug, it ranks the component that mentions
the class three times above the stylesheet that sets the colour, because
counting anchors is all it does. Knowing that colour lives in CSS is
judgment, which is the LLM's job (docs/principles.md #2). A case like that
failing under `--search-only` and passing under the full run is the system
working; both failing means retrieval never surfaced the file at all, and
that is a real bug.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.agents.code_analysis import SYSTEM_PROMPT, _build_context_text
from app.agents.types import (
    AggregatedFinding,
    CodeAnalysisResult,
    FindingLocation,
    FindingPriority,
    FindingSource,
    LocationConfidence,
    SourceLocation,
)
from app.evals.cases import EvalCase, load_cases
from app.evals.scoring import score_location
from app.evals.types import CaseScore, EvalFinding, EvalReport, FindingScore, Outcome
from app.integrations.axe.types import AccessibilityReport
from app.integrations.llm.client import generate_structured
from app.integrations.llm.exceptions import LLMResponseError
from app.integrations.playwright.dom import DomSnapshot
from app.tools.anchors import extract_anchors
from app.tools.repo_search import CandidateMatch, load_source_corpus, search_corpus


async def run_case(case: EvalCase, *, search_only: bool) -> CaseScore:
    corpus = load_source_corpus(case.source_root)
    report = (
        AccessibilityReport.model_validate(case.accessibility_report)
        if case.accessibility_report
        else None
    )
    snapshot = DomSnapshot.model_validate(case.dom_snapshot) if case.dom_snapshot else None

    searched: list[tuple[AggregatedFinding, list[CandidateMatch], list[str]]] = []
    for finding, _ in case.findings:
        anchors = extract_anchors(
            texts=[finding.title, finding.detail, finding.likely_area or ""],
            accessibility_report=report,
            # Mirrors the agent's own rule: an accessibility finding's title
            # *is* the axe rule id, so its evidence narrows to that rule.
            violation_ids=[finding.title] if report and _is_accessibility(finding) else [],
            target_selector=case.target_selector,
            dom_snapshot=snapshot,
        )
        candidates = search_corpus(corpus, anchors)
        searched.append((_as_aggregated(finding), candidates, [anchor.value for anchor in anchors]))

    if search_only:
        locations = [_best_candidate(candidates) for _, candidates, _ in searched]
    else:
        result = await generate_structured(
            system=SYSTEM_PROMPT,
            text=_build_context_text(
                [(finding, candidates) for finding, candidates, _ in searched]
            ),
            images=[],
            output_format=CodeAnalysisResult,
        )
        locations = _align(result, [finding for finding, _, _ in searched])

    return CaseScore(
        case=case.name,
        findings=[
            FindingScore(
                finding_title=finding.title,
                outcome=score_location(expected, location),
                expected=expected,
                actual_file_path=location.location.file_path if location.location else None,
                actual_line_start=location.location.line_start if location.location else None,
                actual_line_end=location.location.line_end if location.location else None,
                anchors=anchors,
                candidate_paths=[candidate.path for candidate in candidates],
            )
            for (_, expected), location, (finding, candidates, anchors) in zip(
                case.findings, locations, searched, strict=True
            )
        ],
    )


def _is_accessibility(finding: EvalFinding) -> bool:
    return finding.source is FindingSource.ACCESSIBILITY


def _as_aggregated(finding: EvalFinding) -> AggregatedFinding:
    """A hand-written EvalFinding as the agent's own input type.

    Priority isn't part of what retrieval reads, so it's filled with a
    constant rather than invented per case — a field a case can set but
    nothing consumes would only mislead whoever writes the next one.
    """
    return AggregatedFinding(
        source=finding.source,
        priority=FindingPriority.HIGH,
        original_severity="high",
        title=finding.title,
        detail=finding.detail,
        likely_area=finding.likely_area,
    )


def _best_candidate(candidates: list[CandidateMatch]) -> FindingLocation:
    """The deterministic half's answer: its top-ranked candidate.

    Scoring the rank-1 candidate rather than "is the answer anywhere in the
    list" on purpose — the list is what the model sees, and a correct
    answer ranked fifth behind four wrong ones is a ranking problem the
    model then has to overcome. Where the model actually rescues such a
    case, the full run scores better than this, which is the interesting
    comparison.
    """
    if not candidates:
        return FindingLocation(
            finding_title="",
            no_match=True,
            explanation="no candidates",
            confidence=LocationConfidence.LOW,
        )
    best = candidates[0]
    return FindingLocation(
        finding_title="",
        no_match=False,
        location=SourceLocation(
            file_path=best.path,
            line_start=best.line_start,
            line_end=best.line_end,
            code_evidence="",
        ),
        explanation="top-ranked candidate",
        confidence=LocationConfidence.MEDIUM,
    )


def _align(result: CodeAnalysisResult, findings: list[AggregatedFinding]) -> list[FindingLocation]:
    """Match the model's answers to the findings by title.

    The prompt asks for one entry per finding in order, but that's a
    request, not a guarantee. Matching by title and treating an absent
    answer as no_match keeps a dropped or reordered entry from silently
    scoring against the wrong finding — which would make the whole report
    wrong rather than one row low.
    """
    by_title = {location.finding_title: location for location in result.locations}
    aligned = []
    for finding in findings:
        aligned.append(
            by_title.get(
                finding.title,
                FindingLocation(
                    finding_title=finding.title,
                    no_match=True,
                    explanation="the model returned no entry for this finding",
                    confidence=LocationConfidence.LOW,
                ),
            )
        )
    return aligned


async def run(cases_root: Path | None, *, search_only: bool) -> EvalReport:
    cases = load_cases(cases_root) if cases_root else load_cases()
    return EvalReport(cases=[await run_case(case, search_only=search_only) for case in cases])


async def run_with_retry(
    cases_root: Path | None, *, search_only: bool, attempts: int = 4
) -> EvalReport:
    """Retry the whole run when the provider is transiently unavailable.

    A free-tier 503 ("experiencing high demand") says nothing about
    retrieval quality, but it does abandon the run — and a harness that
    can't produce a number when the upstream is busy doesn't get used. Only
    LLMResponseError is retried; a bad case file or a missing key should
    fail immediately rather than four times.
    """
    delay = 15.0
    for attempt in range(attempts):
        try:
            return await run(cases_root, search_only=search_only)
        except LLMResponseError:
            if attempt == attempts - 1:
                raise
            print(f"provider unavailable, retrying in {delay:.0f}s", file=sys.stderr)
            await asyncio.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")


def format_report(report: EvalReport, *, search_only: bool) -> str:
    lines = [f"{'deterministic search only' if search_only else 'full retrieval path'}", ""]
    for case in report.cases:
        lines.append(f"{case.case}  {case.correct}/{len(case.findings)}")
        for score in case.findings:
            actual = (
                f"{score.actual_file_path}:{score.actual_line_start}-{score.actual_line_end}"
                if score.actual_file_path
                else "no_match"
            )
            expected = (
                f"{score.expected.file_path}:{score.expected.line_start}-{score.expected.line_end}"
                if score.expected.file_path
                else "no_match"
            )
            mark = "ok  " if score.outcome in _CORRECT else "FAIL"
            lines.append(f"  {mark} {score.outcome.value:18} {score.finding_title}")
            if score.outcome not in _CORRECT:
                lines.append(f"       expected {expected}, got {actual}")
                # Printed only on failure, and this is why: it says whether
                # to go fix anchor extraction or ranking.
                lines.append(f"       anchors: {score.anchors or 'none'}")
                lines.append(f"       candidates: {score.candidate_paths or 'none'}")
        lines.append("")

    lines.append(f"accuracy {report.correct}/{report.total} ({report.accuracy:.0%})")
    for outcome in Outcome:
        count = report.count(outcome)
        if count:
            lines.append(f"  {outcome.value:18} {count}")
    return "\n".join(lines)


_CORRECT = (Outcome.LOCATED, Outcome.CORRECT_NO_MATCH)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--search-only",
        action="store_true",
        help="score the deterministic search without calling an LLM (free, CI-safe)",
    )
    parser.add_argument("--cases", type=Path, default=None, help="directory of eval cases")
    parser.add_argument("--json", action="store_true", help="emit the full report as JSON")
    parser.add_argument(
        "--min-accuracy",
        type=float,
        default=None,
        help="exit non-zero if accuracy falls below this fraction (e.g. 0.9). "
        "Without it the command always succeeds, which is what you want when "
        "reading a report by hand and not what you want in CI.",
    )
    args = parser.parse_args()

    report = asyncio.run(run_with_retry(args.cases, search_only=args.search_only))
    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
    else:
        print(format_report(report, search_only=args.search_only))

    if args.min_accuracy is not None and report.accuracy < args.min_accuracy:
        print(
            f"\nFAIL: accuracy {report.accuracy:.0%} is below the required "
            f"{args.min_accuracy:.0%}.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
