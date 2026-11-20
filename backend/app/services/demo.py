"""The read-only showcase account behind the public deployment.

Why this exists
---------------
Design Drift's workflow needs a real Chromium (Playwright capture, axe-core)
and real model calls. Both are fine on a laptop and fine on a paid instance;
neither is fine on a free public URL, where a single visitor clicking "Run
check" would spend tokens from the owner's key and a crawler hitting it in a
loop would spend rather more.

So the public deployment serves *stored results from real runs* — the
screenshots, diffs, findings, code locations and patches that the agents
actually produced — and refuses to start a new run. That distinction is the
important one, and it is deliberately not hidden: `demo_locked` on the API
response is what the frontend uses to label the demo honestly rather than
pretending a disabled button is a working one (docs/principles.md #2).

What is real in the demo
    Everything shown: the findings, the located files and line numbers, the
    proposed patches, the verification verdict. All produced by the agents
    on a real run against a real deployed site.

What is locked in the demo
    Starting a run, approving/applying/verifying a fix, creating or deleting
    a project. Everything that would either spend money or mutate the
    showcase.

The lock is enforced here, server-side, on the owner of the row rather than
on the caller: it protects the demo account's data whether the request
arrives with no token, with the demo token, or with anybody else's.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.project import Project
from app.models.user import User
from app.services import auth as auth_service

logger = logging.getLogger(__name__)


class DemoReadOnlyError(Exception):
    """A mutating or cost-bearing action was attempted on the demo account.

    Carries the message the API returns verbatim, because the frontend shows
    it to a recruiter who should learn what the demo is, not read a stack of
    internal vocabulary.
    """


async def get_demo_user(db: AsyncSession) -> User | None:
    """The showcase account, or None when demo mode is off or unseeded.

    Returns None rather than raising for the unseeded case: a deployment
    with DEMO_MODE=true but no seed yet should serve a normal, empty app,
    not 500 on every request.
    """
    settings = get_settings()
    if not settings.demo_mode:
        return None
    return await auth_service.get_user_by_email(db, settings.demo_user_email)


async def demo_user_id(db: AsyncSession) -> UUID | None:
    user = await get_demo_user(db)
    return None if user is None else user.id


def is_demo_owned(project: Project, demo_id: UUID | None) -> bool:
    """Whether this project belongs to the showcase account."""
    return demo_id is not None and project.owner_id == demo_id


async def guard_mutation(db: AsyncSession, project: Project, action: str) -> None:
    """Refuse `action` when `project` belongs to the showcase account.

    Called at the top of every route that would spend money or change the
    showcase's stored results. Keyed on the project's owner, not the
    caller's identity, so the demo data is equally protected from an
    anonymous visitor and from a signed-in stranger who guessed the id.
    """
    demo_id = await demo_user_id(db)
    if not is_demo_owned(project, demo_id):
        return
    raise DemoReadOnlyError(
        f"This is the read-only demo project, so {action} is disabled here. "
        "Every result you can see came from a real agent run against the live "
        "site. To execute the agents yourself, sign up and add your own "
        "project, or run Design Drift locally."
    )
