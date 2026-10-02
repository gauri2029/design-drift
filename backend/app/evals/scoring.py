"""Compare a produced location against the hand-verified answer.

Deterministic: whether two line ranges refer to the same code is a fact
about integers, so no model is asked (docs/principles.md #2).
"""

from app.agents.types import FindingLocation
from app.evals.types import ExpectedLocation, Outcome


def score_location(expected: ExpectedLocation, actual: FindingLocation) -> Outcome:
    """Grade one finding's answer.

    The four cases that matter are the asymmetric ones: admitting you
    didn't find something is cheap, and sending a developer to the wrong
    file is expensive, so they can't collapse into one "incorrect" bucket.
    """
    expected_nothing = expected.file_path is None

    if actual.no_match or actual.location is None:
        return Outcome.CORRECT_NO_MATCH if expected_nothing else Outcome.MISSED

    if expected_nothing:
        return Outcome.FALSE_POSITIVE

    if actual.location.file_path != expected.file_path:
        return Outcome.WRONG_FILE

    if not _ranges_overlap(expected, actual):
        return Outcome.WRONG_LINES

    return Outcome.LOCATED


def _ranges_overlap(expected: ExpectedLocation, actual: FindingLocation) -> bool:
    """Whether the located range and the expected one refer to the same code.

    Overlap, not equality. The expected range is a human's judgement of
    "the responsible code", and a model that returns the opening tag where
    the answer says the whole block — or the reverse — has located the
    right thing; grading that as a miss would make the harness punish
    correct answers and reward matching one person's bracketing. What it
    still catches is the real failure: pointing at an unrelated part of the
    right file.
    """
    if expected.line_start is None or expected.line_end is None:
        # A case that names a file but no lines is asserting only "this is
        # the right file", which the caller has already confirmed.
        return True

    assert actual.location is not None
    return (
        actual.location.line_start <= expected.line_end
        and expected.line_start <= actual.location.line_end
    )
