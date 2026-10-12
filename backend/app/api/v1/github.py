"""Read-only GitHub endpoints: link an installation, browse what it grants.

Every route requires a signed-in user and filters on them. Nothing here
writes to GitHub — the App holds `Contents: read-only`, so pushes, commits
and pull requests are refused by GitHub itself.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import require_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.integrations.github import client
from app.integrations.github.exceptions import (
    GitHubNotConfiguredError,
    RepositoryNotPermittedError,
)
from app.models.user import User
from app.schemas.github import (
    GitHubStatus,
    InstallationLink,
    InstallationLinkByAccount,
    InstallationRead,
    RepositoryRead,
)
from app.services import github as github_service

router = APIRouter(prefix="/github", tags=["github"])


def _handle(exc: Exception) -> HTTPException:
    """One mapping from service/client errors to responses.

    GitHubAPIError becomes a 404 rather than a 502: by the time it reaches
    here the caller has asked about a specific repository, and "GitHub said
    no" and "you can't see it" should look identical from outside.
    """
    if isinstance(exc, GitHubNotConfiguredError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if isinstance(exc, github_service.InstallationAlreadyLinkedError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, github_service.InstallationNotLinkedError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, RepositoryNotPermittedError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/status", response_model=GitHubStatus)
async def github_status(_: User = Depends(require_current_user)) -> GitHubStatus:
    """Lets the UI offer GitHub only when the server can actually do it."""
    settings = get_settings()
    if not client.is_configured() or not settings.github_app_slug:
        return GitHubStatus(configured=False)
    return GitHubStatus(
        configured=True,
        install_url=f"https://github.com/apps/{settings.github_app_slug}/installations/new",
    )


@router.get("/installations", response_model=list[InstallationRead])
async def list_installations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
) -> list[InstallationRead]:
    records = await github_service.list_installations(db, user.id)
    return [InstallationRead.model_validate(r, from_attributes=True) for r in records]


@router.post("/installations", response_model=InstallationRead, status_code=status.HTTP_201_CREATED)
async def link_installation(
    payload: InstallationLink,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
) -> InstallationRead:
    """Record an installation after GitHub redirects back from the install.

    The id arrives from the browser's query string, so it is verified
    against GitHub before being stored — see services.github.link_installation.
    """
    try:
        record = await github_service.link_installation(db, user.id, payload.installation_id)
    except Exception as exc:
        raise _handle(exc) from exc
    return InstallationRead.model_validate(record, from_attributes=True)


@router.post(
    "/installations/by-account",
    response_model=InstallationRead,
    status_code=status.HTTP_201_CREATED,
)
async def link_installation_by_account(
    payload: InstallationLinkByAccount,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
) -> InstallationRead:
    """Link an installation GitHub didn't hand us an id for.

    GitHub's "Configure" flow returns the user without an installation_id,
    so the normal callback can't fire and the App looks unconnected even
    though it is installed. Naming the account recovers it.
    """
    try:
        record = await github_service.link_installation_by_account(
            db, user.id, payload.account_login
        )
    except Exception as exc:
        raise _handle(exc) from exc
    return InstallationRead.model_validate(record, from_attributes=True)


@router.get("/installations/{installation_id}/repositories", response_model=list[RepositoryRead])
async def list_repositories(
    installation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
) -> list[RepositoryRead]:
    try:
        await github_service.require_installation(db, user.id, installation_id)
        repositories = await client.list_repositories(installation_id)
    except Exception as exc:
        raise _handle(exc) from exc

    out: list[RepositoryRead] = []
    for repository in repositories:
        try:
            client.assert_analyzable(repository)
            analyzable, reason = True, None
        except RepositoryNotPermittedError as exc:
            analyzable, reason = False, str(exc)
        out.append(
            RepositoryRead(
                full_name=str(repository.get("full_name", "")),
                private=bool(repository.get("private")),
                default_branch=str(repository.get("default_branch") or "main"),
                analyzable=analyzable,
                reason=reason,
            )
        )
    return out


@router.get("/installations/{installation_id}/repositories/{owner}/{repo}/branches")
async def list_branches(
    installation_id: int,
    owner: str,
    repo: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
) -> list[str]:
    try:
        await github_service.require_installation(db, user.id, installation_id)
        return await client.list_branches(installation_id, f"{owner}/{repo}")
    except Exception as exc:
        raise _handle(exc) from exc
