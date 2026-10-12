"""Read-only GitHub App access: installations, repositories, branches, clone.

Authentication is two-legged and deliberately stateless:

    App JWT (RS256, signed with the App's private key, 10 min)
      -> POST /app/installations/{id}/access_tokens
      -> installation token (~1 hour, scoped to that installation)

Neither is ever persisted. The installation token is minted per operation,
used, and dropped when the function returns — so a database dump contains
nothing that can reach anyone's repository, and revoking the App's
installation takes effect immediately rather than when a stored token
expires.

The App is registered with `Contents: read-only`, so push, PR creation and
any other write are refused by GitHub itself, not merely absent from this
module.
"""

import asyncio
import time
from pathlib import Path
from typing import Any

import httpx
import jwt

from app.core.config import get_settings
from app.integrations.github.exceptions import (
    GitHubAPIError,
    GitHubNotConfiguredError,
    RepositoryNotPermittedError,
)

API_BASE = "https://api.github.com"
_ACCEPT = "application/vnd.github+json"
_TIMEOUT = 30.0

# A clone has to finish in a time a user will wait through, and an
# unbounded one is a way to hang a worker on a deliberately huge repo.
_CLONE_TIMEOUT_SECONDS = 120.0

# GitHub's cap is 10 minutes; staying under it avoids clock-skew rejections.
_JWT_LIFETIME_SECONDS = 540


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.github_app_id and settings.github_app_private_key_path)


def _app_jwt() -> str:
    """A short-lived JWT identifying the App itself (not any installation)."""
    settings = get_settings()
    if not is_configured():
        raise GitHubNotConfiguredError(
            "GitHub is not configured. Set GITHUB_APP_ID and "
            "GITHUB_APP_PRIVATE_KEY_PATH, or use a local source path instead."
        )

    key_path = Path(settings.github_app_private_key_path).expanduser()
    try:
        private_key = key_path.read_text()
    except OSError as exc:
        raise GitHubNotConfiguredError(
            f"the GitHub App private key could not be read from {key_path}"
        ) from exc

    now = int(time.time())
    return jwt.encode(
        # `iat` is backdated by a minute because GitHub rejects a token
        # whose issue time is even slightly in its future.
        {"iat": now - 60, "exp": now + _JWT_LIFETIME_SECONDS, "iss": settings.github_app_id},
        private_key,
        algorithm="RS256",
    )


async def _request(url: str, token: str, *, as_app: bool = False) -> Any:
    headers = {"Accept": _ACCEPT, "Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(url, headers=headers)
    if response.status_code == 404:
        # Also what GitHub returns for "exists but this App can't see it",
        # which is the answer we want to give anyway.
        raise GitHubAPIError("not found, or this installation has no access to it")
    if response.status_code >= 400:
        # Deliberately not echoing the body: it can quote the request's
        # Authorization header back in some error shapes.
        raise GitHubAPIError(f"GitHub request failed with status {response.status_code}")
    return response.json()


async def installation_token(installation_id: int) -> str:
    """A ~1-hour token for one installation. Never stored or logged."""
    headers = {"Accept": _ACCEPT, "Authorization": f"Bearer {_app_jwt()}"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(
            f"{API_BASE}/app/installations/{installation_id}/access_tokens", headers=headers
        )
    if response.status_code >= 400:
        raise GitHubAPIError(
            f"could not get an access token for installation {installation_id} "
            f"(status {response.status_code})"
        )
    token = response.json().get("token")
    if not isinstance(token, str) or not token:
        raise GitHubAPIError("GitHub returned no installation token")
    return token


async def get_installation(installation_id: int) -> dict[str, Any]:
    """The installation's own record, read with the App's JWT.

    This is what proves an installation id is real and belongs to the
    account the caller claims — the frontend's word for it is never enough
    (see app.services.github.link_installation).
    """
    data = await _request(
        f"{API_BASE}/app/installations/{installation_id}", _app_jwt(), as_app=True
    )
    if not isinstance(data, dict):
        raise GitHubAPIError("unexpected installation payload")
    return data


async def find_installation_by_account(account_login: str) -> dict[str, Any] | None:
    """The App's installation on a named GitHub account, if there is one.

    Exists for the case GitHub leaves no other route to: its "Configure"
    flow returns the user to the app *without* an installation_id, so
    someone who installed the App before signing in — or who reconfigured
    an existing installation — has no id to hand over.

    Takes a login rather than returning the whole list because the App's
    JWT can see every installation of this App, including other people's.
    Matching one the caller already named discloses nothing they did not
    already know; returning the list would be an enumeration of this App's
    users.
    """
    installations = await _request(f"{API_BASE}/app/installations?per_page=100", _app_jwt())
    if not isinstance(installations, list):
        raise GitHubAPIError("unexpected installations payload")
    wanted = account_login.strip().lstrip("@").lower()
    for installation in installations:
        if not isinstance(installation, dict):
            continue
        account = installation.get("account") or {}
        if str(account.get("login", "")).lower() == wanted:
            result: dict[str, Any] = installation
            return result
    return None


async def list_repositories(installation_id: int) -> list[dict[str, Any]]:
    """Exactly the repositories this installation was granted.

    Not "the user's repositories" — the installation's. If someone selected
    three repos when installing, those three are all that is ever visible.
    """
    token = await installation_token(installation_id)
    data = await _request(f"{API_BASE}/installation/repositories?per_page=100", token)
    repositories = data.get("repositories", []) if isinstance(data, dict) else []
    return [r for r in repositories if isinstance(r, dict)]


async def get_repository(installation_id: int, full_name: str) -> dict[str, Any]:
    token = await installation_token(installation_id)
    data = await _request(f"{API_BASE}/repos/{full_name}", token)
    if not isinstance(data, dict):
        raise GitHubAPIError("unexpected repository payload")
    return data


async def list_branches(installation_id: int, full_name: str) -> list[str]:
    token = await installation_token(installation_id)
    data = await _request(f"{API_BASE}/repos/{full_name}/branches?per_page=100", token)
    if not isinstance(data, list):
        raise GitHubAPIError("unexpected branches payload")
    return [b["name"] for b in data if isinstance(b, dict) and isinstance(b.get("name"), str)]


def assert_analyzable(repository: dict[str, Any]) -> None:
    """Refuse a private repository, for now.

    Analysis sends matched source snippets to a third-party LLM. The free
    Gemini tier's terms don't offer the confidentiality guarantees private
    code needs, so this is a deliberate V1 limit rather than an oversight —
    the App may legitimately be installed on private repos, and listing
    them is fine; selecting one for analysis is what's refused.

    Lifting this is a terms decision, not a code change: once an LLM
    provider with suitable terms is configured, this check is where that
    policy lives.
    """
    if repository.get("private"):
        raise RepositoryNotPermittedError(
            "Design Drift currently analyzes public repositories only. Analysis sends "
            "matched source snippets to a third-party LLM, and the configured provider's "
            "terms aren't suitable for private code yet. Use a local source path for "
            "private repositories."
        )


async def clone(*, installation_id: int, full_name: str, branch: str, destination: Path) -> str:
    """Shallow-clone one branch into `destination`. Returns the commit SHA.

    The token goes in the URL because that is how git authenticates over
    HTTPS, which means it must never be logged: the subprocess's stderr is
    captured and only a fixed message is raised, never the command line.
    """
    token = await installation_token(installation_id)
    url = f"https://x-access-token:{token}@github.com/{full_name}.git"

    destination.parent.mkdir(parents=True, exist_ok=True)
    process = await asyncio.create_subprocess_exec(
        "git",
        "clone",
        "--depth",
        "1",
        "--single-branch",
        "--branch",
        branch,
        # Repository content is never executed, but a hook or a filter
        # configured by the repo would be. Both are refused outright.
        "--config",
        "core.hooksPath=/dev/null",
        "--config",
        "filter.lfs.process=",
        url,
        str(destination),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=_CLONE_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        process.kill()
        raise GitHubAPIError(f"cloning {full_name} timed out") from exc

    if process.returncode != 0:
        # stderr can contain the tokenized URL, so it is not propagated.
        raise GitHubAPIError(
            f"could not clone {full_name} at branch {branch!r} "
            "(check the branch exists and the installation still has access)"
        )
    return await _head_sha(destination)


async def _head_sha(repository: Path) -> str:
    process = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(repository),
        "rev-parse",
        "HEAD",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        raise GitHubAPIError("could not read the cloned commit SHA")
    return stdout.decode().strip()
