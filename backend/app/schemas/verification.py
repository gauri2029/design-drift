"""Request body for triggering verification."""

from pydantic import BaseModel, Field


class VerificationRequest(BaseModel):
    # Overrides the project's own target_url for this check only, and is
    # not stored. Patches are applied to a local checkout, so a project
    # pointing at a deployed site can't show the change until it's
    # rebuilt — verifying against a local dev server is the honest way to
    # check a fix before shipping it.
    target_url: str | None = Field(default=None, pattern=r"^https?://")
