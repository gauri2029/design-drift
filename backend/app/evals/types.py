"""Contracts for the retrieval eval harness (docs/architecture.md's
`evals/` — Phase 8).

What this measures and why: the Code Analysis retrieval path has been
changed four times (three anchor iterations, then DOM extraction), and each
change was judged by running one real site and reading the output. That
can't answer "did this improve location accuracy, or just move it?", and it
can't catch a change that helps one codebase by hurting another. These
types are the vocabulary for answering that with a number.

Scoring is deterministic — no LLM judge. A location is right or wrong
against a hand-verified answer, which is a fact, so it's computed
(docs/principles.md #2). That also keeps the harness free of the thing it
is supposed to be measuring.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from app.agents.types import FindingSource


class EvalFinding(BaseModel):
    """One finding to locate, standing in for an AggregatedFinding.

    Only the fields retrieval actually reads. Written by hand per case
    rather than produced by a run, so a retrieval regression can't hide
    behind an upstream agent wording a finding differently that day.
    """

    title: str
    detail: str
    likely_area: str | None = None
    source: FindingSource


class ExpectedLocation(BaseModel):
    """The hand-verified answer for one finding."""

    # None means "there is genuinely nothing in this checkout to find, and
    # no_match is the correct answer". Scoring it is the point: a system
    # that locates everything by guessing is worse than one that admits
    # when the evidence isn't there.
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    # Why this is the answer. Not scored — it's for whoever reads a failure
    # and has to decide whether the case or the code is wrong.
    rationale: str = ""


class Outcome(StrEnum):
    """How one finding's answer compares to the expected one.

    Deliberately more than pass/fail: "named the wrong file" and "named the
    right file but the wrong lines" call for different fixes — the first is
    a ranking problem in the search, the second is the model misreading a
    snippet it was shown.
    """

    LOCATED = "located"
    WRONG_FILE = "wrong_file"
    WRONG_LINES = "wrong_lines"
    # Said no_match where a real location existed. A miss, but an honest
    # one, and tracked apart from a confident wrong answer because the cost
    # to a developer is lower.
    MISSED = "missed"
    # Correctly said no_match where there was nothing to find.
    CORRECT_NO_MATCH = "correct_no_match"
    # Invented a location where none existed — the most expensive outcome,
    # since it sends someone to a file for nothing.
    FALSE_POSITIVE = "false_positive"


class FindingScore(BaseModel):
    finding_title: str
    outcome: Outcome
    expected: ExpectedLocation
    actual_file_path: str | None = None
    actual_line_start: int | None = None
    actual_line_end: int | None = None
    # Which anchors the search produced, so a failure can be read without
    # re-running: no anchors means the extraction step is at fault, good
    # anchors with the wrong file means ranking is.
    anchors: list[str] = Field(default_factory=list)
    candidate_paths: list[str] = Field(default_factory=list)


class CaseScore(BaseModel):
    case: str
    findings: list[FindingScore]

    @property
    def correct(self) -> int:
        return sum(
            1
            for score in self.findings
            if score.outcome in (Outcome.LOCATED, Outcome.CORRECT_NO_MATCH)
        )


class EvalReport(BaseModel):
    cases: list[CaseScore]

    @property
    def total(self) -> int:
        return sum(len(case.findings) for case in self.cases)

    @property
    def correct(self) -> int:
        return sum(case.correct for case in self.cases)

    def count(self, outcome: Outcome) -> int:
        return sum(1 for case in self.cases for score in case.findings if score.outcome is outcome)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0
