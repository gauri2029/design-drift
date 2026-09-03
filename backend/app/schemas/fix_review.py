"""A human's decision on the Fix Agent's proposed patches.

This is the pause in docs/architecture.md's target flow — the point
docs/principles.md #5 requires before anything is applied. It is
deliberately *not* in app.agents.types: everything there is an agent's
output contract, and this is the one record in the run written by a
person rather than produced by a node.

The decision is stored, not acted on. Nothing in this codebase writes to a
checkout yet, so an approval currently means "a human reviewed this patch
and signed off on it" — the durable input the later apply/verify slice
will consume, and an audit trail either way.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class FixDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class FixDecisionItem(BaseModel):
    finding_title: str
    decision: FixDecision
    # Why the reviewer decided this way. Optional, but the reason a
    # rejection happened is usually worth more later than the rejection.
    note: str | None = None


class FixReviewRequest(BaseModel):
    decisions: list[FixDecisionItem] = Field(min_length=1)


class FixReview(BaseModel):
    """What gets persisted on the run. Replaced wholesale on re-review."""

    decisions: list[FixDecisionItem]
    reviewed_at: datetime
