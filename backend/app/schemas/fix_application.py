"""The record of what was actually written to a source checkout.

Separate from app.schemas.fix_review because they answer different
questions and are written at different times: the review is what a human
decided, this is what happened when we tried to act on that decision. A
patch can be approved and still not applied — the file may have changed in
between — so conflating the two would lose exactly the case worth seeing.
"""

from datetime import datetime

from pydantic import BaseModel


class AppliedFix(BaseModel):
    finding_title: str
    file_path: str
    applied: bool
    # Why it wasn't, when it wasn't. Null on success.
    reason: str | None = None
    # Where this file's pre-patch contents were kept, relative to the
    # checkout. Surfaced rather than left as a convention someone has to
    # know, because it's the answer to "how do I undo this" — and for a
    # checkout that isn't a git clone, it's the only answer.
    backup_path: str | None = None


class FixApplication(BaseModel):
    applied_at: datetime
    fixes: list[AppliedFix]
