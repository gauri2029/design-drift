"""Linking GitHub App installations to accounts, and reading what they grant.

Every function takes the acting user and filters on them. The rule
throughout: an installation id arriving from the frontend is a claim, not a
fact. It is checked against GitHub (does it exist?) and against this table
(has this user linked it?) before it is ever used to read a repository.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.github import client
from app.integrations.github.exceptions import GitHubAPIError
from app.models.github_installation import GitHubInstallation


class InstallationNotLinkedError(Exception):
    """The acting user has not linked this installation."""


class InstallationAlreadyLinkedError(Exception):
    """Another account has already linked this installation."""


async def list_installations(db: AsyncSession, user_id: UUID) -> list[GitHubInstallation]:
    result = await db.execute(
        select(GitHubInstallation)
        .where(GitHubInstallation.user_id == user_id)
        .order_by(GitHubInstallation.created_at.desc())
    )
    return list(result.scalars().all())


async def link_installation(
    db: AsyncSession, user_id: UUID, installation_id: int
) -> GitHubInstallation:
    """Record that `user_id` administers `installation_id`.

    Called after GitHub redirects back from the install flow, with an id
    taken from the query string — i.e. a value the user's browser handed
    us, which another user could just as easily type.

    Two checks make that safe:

    1. The installation is fetched from GitHub with the App's own JWT. A
       made-up id fails here, so only installations of *this App* count.
    2. The id is unique in this table. An installation already linked to
       someone else is refused rather than silently re-pointed, so a second
       user cannot attach themselves to an installation they merely know
       the number of.

    What this deliberately does not claim is that the person completing the
    flow is the GitHub account that owns the installation. Proving that
    needs the user-to-server OAuth exchange. What it does guarantee is that
    an installation reaches exactly one Design Drift account — the first to
    complete the flow — and that nobody else can read through it.
    """
    try:
        installation = await client.get_installation(installation_id)
    except GitHubAPIError as exc:
        raise InstallationNotLinkedError(
            "that installation could not be verified with GitHub"
        ) from exc

    existing = (
        await db.execute(
            select(GitHubInstallation).where(GitHubInstallation.installation_id == installation_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.user_id != user_id:
            raise InstallationAlreadyLinkedError(
                "that GitHub installation is already linked to another account"
            )
        return existing

    account = installation.get("account") or {}
    record = GitHubInstallation(
        user_id=user_id,
        installation_id=installation_id,
        account_login=str(account.get("login") or "unknown"),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def link_installation_by_account(
    db: AsyncSession, user_id: UUID, account_login: str
) -> GitHubInstallation:
    """Link the App's installation on a named account.

    The path for someone GitHub sent back without an installation_id — its
    "Configure" flow omits it, so the normal callback can't fire. Naming
    the account is the proof: the lookup only matches an installation the
    caller already identified, and link_installation still refuses one
    another user has claimed.
    """
    installation = await client.find_installation_by_account(account_login)
    if installation is None:
        raise InstallationNotLinkedError(
            f"Design Drift is not installed on {account_login!r}. Install it there first, "
            "then try again."
        )
    return await link_installation(db, user_id, int(installation["id"]))


async def require_installation(
    db: AsyncSession, user_id: UUID, installation_id: int
) -> GitHubInstallation:
    """The user's linked installation, or raise.

    Every repository read goes through here first, so "can this account
    use this installation" is answered in one place rather than per route.
    """
    record = (
        await db.execute(
            select(GitHubInstallation).where(
                GitHubInstallation.installation_id == installation_id,
                GitHubInstallation.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise InstallationNotLinkedError("no such GitHub installation is linked to your account")
    return record


async def installation_for_repository(db: AsyncSession, user_id: UUID, full_name: str) -> int:
    """Which of the user's installations can reach `full_name`.

    A project stores the repository name but not the installation, so that
    unlinking an installation immediately stops every project that relied
    on it — rather than leaving a stored id that no longer authorizes
    anything but still looks valid.
    """
    for record in await list_installations(db, user_id):
        repositories = await client.list_repositories(record.installation_id)
        if any(r.get("full_name") == full_name for r in repositories):
            return record.installation_id
    raise InstallationNotLinkedError(
        f"none of your linked GitHub installations can access {full_name}"
    )
