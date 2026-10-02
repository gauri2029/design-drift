"""Tests for the eval harness (app.evals).

The harness is the thing that will be trusted to say whether a retrieval
change helped, so its scoring has to be right before its numbers mean
anything. These cover the asymmetric outcomes and the overlap rule, plus
one end-to-end run of the deterministic path over a tiny fixture.
"""

import json
import re

import pytest

from app.agents.types import FindingLocation, FindingSource, LocationConfidence, SourceLocation
from app.evals.cases import CASES_ROOT, load_case
from app.evals.retrieval import run_case
from app.evals.scoring import score_location
from app.evals.types import ExpectedLocation, Outcome


def _located(file_path: str, line_start: int, line_end: int) -> FindingLocation:
    return FindingLocation(
        finding_title="t",
        no_match=False,
        location=SourceLocation(
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            code_evidence="x",
        ),
        explanation="e",
        confidence=LocationConfidence.HIGH,
    )


def _no_match() -> FindingLocation:
    return FindingLocation(
        finding_title="t", no_match=True, explanation="e", confidence=LocationConfidence.LOW
    )


def test_an_overlapping_range_counts_as_located() -> None:
    """The expected range is one person's bracketing of "the responsible
    code". A model returning the opening tag where the answer says the
    whole block has found the right thing, and grading that as a miss would
    make the harness punish correct answers."""
    expected = ExpectedLocation(file_path="index.html", line_start=26, line_end=34)

    assert score_location(expected, _located("index.html", 26, 26)) is Outcome.LOCATED
    assert score_location(expected, _located("index.html", 20, 60)) is Outcome.LOCATED


def test_a_non_overlapping_range_in_the_right_file_is_wrong_lines() -> None:
    """Distinguished from wrong_file because it needs a different fix: the
    search found the right file, the model misread which part of it."""
    expected = ExpectedLocation(file_path="index.html", line_start=26, line_end=34)

    assert score_location(expected, _located("index.html", 167, 215)) is Outcome.WRONG_LINES


def test_the_wrong_file_is_its_own_outcome() -> None:
    expected = ExpectedLocation(file_path="index.html", line_start=14, line_end=14)

    assert score_location(expected, _located("index.css", 1, 45)) is Outcome.WRONG_FILE


def test_admitting_a_miss_is_scored_apart_from_a_confident_wrong_answer() -> None:
    """Both are failures, and they cost a developer differently: no_match
    wastes nothing, a wrong location sends someone to a file for nothing."""
    real = ExpectedLocation(file_path="index.html", line_start=2, line_end=2)
    nothing = ExpectedLocation(file_path=None)

    assert score_location(real, _no_match()) is Outcome.MISSED
    assert score_location(nothing, _located("index.html", 2, 2)) is Outcome.FALSE_POSITIVE
    assert score_location(nothing, _no_match()) is Outcome.CORRECT_NO_MATCH


def test_a_case_naming_a_file_but_no_lines_asserts_only_the_file() -> None:
    expected = ExpectedLocation(file_path="index.html")

    assert score_location(expected, _located("index.html", 999, 1000)) is Outcome.LOCATED
    assert score_location(expected, _located("other.html", 1, 1)) is Outcome.WRONG_FILE


@pytest.fixture
def tiny_case(tmp_path):
    """A two-file checkout with one findable finding and one unfindable."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "index.html").write_text(
        '<html>\n<body>\n<button id="buy-now">Buy now</button>\n</body>\n</html>\n'
    )
    (source / "styles.css").write_text(".unrelated { color: red; }\n")
    (tmp_path / "case.json").write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "finding": {
                            "title": "Button label is wrong",
                            "detail": "The button reads 'Buy now' but the design says 'Subscribe'.",
                            "source": FindingSource.VISUAL_COMPARISON.value,
                        },
                        "expected": {"file_path": "index.html", "line_start": 3, "line_end": 3},
                    },
                    {
                        "finding": {
                            "title": "Footer is missing",
                            "detail": "The design shows a footer with contact details.",
                            "source": FindingSource.VISUAL_COMPARISON.value,
                        },
                        "expected": {"file_path": None},
                    },
                ]
            }
        )
    )
    return load_case(tmp_path)


async def test_the_deterministic_half_runs_without_an_llm_or_a_key(tiny_case) -> None:
    """--search-only is the mode meant for CI, so it must not touch a
    provider: no API key is configured here and this still scores."""
    score = await run_case(tiny_case, search_only=True)

    assert score.case == tiny_case.source_root.parent.name
    assert [finding.outcome for finding in score.findings] == [
        Outcome.LOCATED,
        Outcome.CORRECT_NO_MATCH,
    ]


async def test_a_failure_records_the_anchors_and_candidates_behind_it(tiny_case) -> None:
    """So a regression can be diagnosed from the report alone: no anchors
    means anchor extraction is at fault, good anchors with the wrong file
    means ranking is."""
    score = await run_case(tiny_case, search_only=True)

    located = score.findings[0]
    assert "Buy now" in located.anchors
    assert located.candidate_paths == ["index.html"]
    # The unfindable one legitimately produces nothing to search with.
    assert score.findings[1].candidate_paths == []


# --- the committed cases, as a regression guard -----------------------------
#
# These pin the deterministic score so the three ranking bugs the harness
# found can't silently come back. Deliberately asserting the per-case
# outcome rather than a single total: a total can stay flat while one case
# improves and another regresses.


async def test_the_static_page_case_locates_every_finding_deterministically() -> None:
    """7/7 without an LLM. Was 5/7 before the harness existed — see
    app/evals/README.md for the three bugs behind those two failures."""
    case = load_case(CASES_ROOT / "static-page")

    score = await run_case(case, search_only=True)

    failures = [
        (finding.finding_title, finding.outcome.value)
        for finding in score.findings
        if finding.outcome not in (Outcome.LOCATED, Outcome.CORRECT_NO_MATCH)
    ]
    assert failures == []


async def test_the_component_case_surfaces_the_stylesheet_even_where_it_ranks_second() -> None:
    """The contrast finding's cause is in CSS while the element is in
    markup, and the search legitimately ranks the component first — picking
    between them is judgment, so it's the LLM's job. What retrieval must
    guarantee is that the stylesheet reaches the candidates at all; if it
    didn't, no model could choose it."""
    case = load_case(CASES_ROOT / "component-app")

    score = await run_case(case, search_only=True)
    contrast = next(f for f in score.findings if f.finding_title == "color-contrast")

    assert contrast.outcome is Outcome.WRONG_FILE
    assert "src/components/Button.css" in contrast.candidate_paths


async def test_both_committed_cases_know_when_to_stop() -> None:
    """A no_match case per codebase shape. Without these, a system that
    always guesses would score as well as one that admits the evidence
    isn't there."""
    for name in ("static-page", "component-app"):
        score = await run_case(load_case(CASES_ROOT / name), search_only=True)
        no_match_cases = [
            finding for finding in score.findings if finding.expected.file_path is None
        ]
        assert no_match_cases, f"{name} has no unanswerable case"
        assert all(finding.outcome is Outcome.CORRECT_NO_MATCH for finding in no_match_cases), (
            f"{name} invented a location where there was nothing to find"
        )


def test_no_eval_fixture_points_at_a_real_third_party_site() -> None:
    """Fixtures must be synthetic.

    Target-app source belongs to whoever owns it — `sources/` is gitignored
    for that reason, and `app/evals/cases/` must not become a way to commit
    it anyway. A real site's markup was copied in here once; this is the
    guard against doing it again. Checked by host rather than by content,
    since a real page is recognisable by what it links to long before
    anyone reads it.
    """
    reserved = ("example.org", "example.com", "example.test", "localhost", "127.0.0.1")
    offenders = []

    for path in CASES_ROOT.rglob("*"):
        if not path.is_file():
            continue
        for match in re.finditer(r"https?://([^/\s\"')]+)", path.read_text()):
            host = match.group(1)
            # Font and spec hosts a hand-written fixture legitimately cites.
            if host.endswith(("dequeuniversity.com", "fonts.googleapis.com", "w3.org")):
                continue
            if not host.endswith(reserved):
                offenders.append(f"{path.relative_to(CASES_ROOT)}: {host}")

    assert offenders == [], (
        "eval fixtures must not reference real sites — use example.org. Found: " f"{offenders}"
    )
