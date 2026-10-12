"""Security properties of the GitHub integration.

Written as attacks rather than as feature coverage: each test is a thing
someone could try, and the assertion is that it doesn't work.
"""

import uuid
from pathlib import Path

import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.integrations.github import client
from app.integrations.github.exceptions import GitHubAPIError, RepositoryNotPermittedError
from app.main import app
from app.models.github_installation import GitHubInstallation
from app.models.user import User
from app.services.workspace import reset, workspace_for
from app.tools.repo_search import SourceNotAccessibleError, list_source_files

pytestmark = pytest.mark.anonymous

ALICE_INSTALLATION = 111
BOB_INSTALLATION = 222


@pytest.fixture
def configured_app(monkeypatch, tmp_path):
    """A GitHub App that exists, so routes get past the "not configured" gate."""
    key = tmp_path / "key.pem"
    key.write_text(_TEST_PRIVATE_KEY)
    monkeypatch.setattr(get_settings(), "github_app_id", "12345")
    monkeypatch.setattr(get_settings(), "github_app_private_key_path", str(key))
    monkeypatch.setattr(get_settings(), "github_app_slug", "design-drift-test")


@pytest.fixture(autouse=True)
async def _clean_up():
    yield
    app.dependency_overrides.clear()
    async with async_session_factory() as session:
        await session.execute(delete(GitHubInstallation))
        await session.execute(delete(User))
        await session.commit()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _signup(http: AsyncClient, email: str) -> dict[str, str]:
    response = await http.post(
        "/api/v1/auth/signup",
        json={"email": email, "name": email.split("@")[0], "password": "a good long password"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _link(user_email: str, installation_id: int) -> None:
    """Link an installation directly, bypassing the GitHub round trip."""
    async with async_session_factory() as session:
        user = (
            await session.execute(
                delete(GitHubInstallation).where(
                    GitHubInstallation.installation_id == installation_id
                )
            )
        ) and None
        from sqlalchemy import select

        owner = (await session.execute(select(User).where(User.email == user_email))).scalar_one()
        session.add(
            GitHubInstallation(
                user_id=owner.id, installation_id=installation_id, account_login="acct"
            )
        )
        await session.commit()
    assert user is None  # the delete above is only a tidy-up


class TestInstallationAuthorization:
    """An installation id from the frontend is a claim, not a fact."""

    async def test_another_users_installation_cannot_be_browsed(self):
        async with _client() as http:
            await _signup(http, "alice@example.com")
            bob = await _signup(http, "bob@example.com")
            await _link("alice@example.com", ALICE_INSTALLATION)

            # Bob knows (or guesses) Alice's installation number.
            response = await http.get(
                f"/api/v1/github/installations/{ALICE_INSTALLATION}/repositories",
                headers=bob,
            )

        # 404, not 403: confirming it exists would be the leak.
        assert response.status_code == 404

    async def test_branches_are_gated_by_the_same_check(self):
        async with _client() as http:
            await _signup(http, "alice@example.com")
            bob = await _signup(http, "bob@example.com")
            await _link("alice@example.com", ALICE_INSTALLATION)

            response = await http.get(
                f"/api/v1/github/installations/{ALICE_INSTALLATION}/repositories/o/r/branches",
                headers=bob,
            )

        assert response.status_code == 404

    async def test_installations_are_listed_per_account(self):
        async with _client() as http:
            alice = await _signup(http, "alice@example.com")
            bob = await _signup(http, "bob@example.com")
            await _link("alice@example.com", ALICE_INSTALLATION)
            await _link("bob@example.com", BOB_INSTALLATION)

            seen_by_alice = (await http.get("/api/v1/github/installations", headers=alice)).json()
            seen_by_bob = (await http.get("/api/v1/github/installations", headers=bob)).json()

        assert [i["installation_id"] for i in seen_by_alice] == [ALICE_INSTALLATION]
        assert [i["installation_id"] for i in seen_by_bob] == [BOB_INSTALLATION]

    async def test_every_github_route_requires_a_token(self):
        async with _client() as http:
            for method, path in (
                ("GET", "/api/v1/github/status"),
                ("GET", "/api/v1/github/installations"),
                ("POST", "/api/v1/github/installations"),
                ("GET", f"/api/v1/github/installations/{ALICE_INSTALLATION}/repositories"),
            ):
                response = await http.request(method, path, json={"installation_id": 1})
                assert response.status_code == 401, f"{method} {path}"

    @respx.mock
    async def test_an_installation_already_linked_elsewhere_is_refused(self, configured_app):
        """Otherwise a second account could attach itself to someone's repos."""
        respx.get(f"https://api.github.com/app/installations/{ALICE_INSTALLATION}").mock(
            return_value=Response(200, json={"account": {"login": "alice"}})
        )
        async with _client() as http:
            await _signup(http, "alice@example.com")
            bob = await _signup(http, "bob@example.com")
            await _link("alice@example.com", ALICE_INSTALLATION)

            response = await http.post(
                "/api/v1/github/installations",
                json={"installation_id": ALICE_INSTALLATION},
                headers=bob,
            )

        assert response.status_code == 409

    @respx.mock
    async def test_an_unverifiable_installation_id_is_rejected(self, configured_app):
        """A made-up number must not become a linked installation."""
        respx.get("https://api.github.com/app/installations/999999").mock(
            return_value=Response(404, json={"message": "Not Found"})
        )
        async with _client() as http:
            alice = await _signup(http, "alice@example.com")
            response = await http.post(
                "/api/v1/github/installations",
                json={"installation_id": 999999},
                headers=alice,
            )

        assert response.status_code == 404
        async with async_session_factory() as session:
            from sqlalchemy import func, select

            count = (
                await session.execute(select(func.count()).select_from(GitHubInstallation))
            ).scalar()
        assert count == 0


class TestLinkingByAccountName:
    """The recovery path for GitHub's Configure flow, which returns the
    user with no installation_id."""

    @respx.mock
    async def test_naming_your_account_links_its_installation(self, configured_app):
        respx.get("https://api.github.com/app/installations").mock(
            return_value=Response(
                200,
                json=[
                    {"id": BOB_INSTALLATION, "account": {"login": "bob"}},
                    {"id": ALICE_INSTALLATION, "account": {"login": "alice"}},
                ],
            )
        )
        respx.get(f"https://api.github.com/app/installations/{ALICE_INSTALLATION}").mock(
            return_value=Response(200, json={"account": {"login": "alice"}})
        )

        async with _client() as http:
            alice = await _signup(http, "alice@example.com")
            response = await http.post(
                "/api/v1/github/installations/by-account",
                json={"account_login": "Alice"},  # case shouldn't matter
                headers=alice,
            )

        assert response.status_code == 201
        assert response.json()["installation_id"] == ALICE_INSTALLATION

    @respx.mock
    async def test_it_never_returns_the_list_of_other_installations(self, configured_app):
        """The App's JWT can see every installation of this App. Naming one
        you already know discloses nothing; enumerating them would."""
        respx.get("https://api.github.com/app/installations").mock(
            return_value=Response(200, json=[{"id": BOB_INSTALLATION, "account": {"login": "bob"}}])
        )

        async with _client() as http:
            alice = await _signup(http, "alice@example.com")
            response = await http.post(
                "/api/v1/github/installations/by-account",
                json={"account_login": "alice"},
                headers=alice,
            )

        assert response.status_code == 404
        # Not even the fact that an installation named "bob" exists.
        assert "bob" not in response.text
        assert str(BOB_INSTALLATION) not in response.text

    @respx.mock
    async def test_you_cannot_claim_an_account_someone_else_linked(self, configured_app):
        respx.get("https://api.github.com/app/installations").mock(
            return_value=Response(
                200, json=[{"id": ALICE_INSTALLATION, "account": {"login": "alice"}}]
            )
        )
        respx.get(f"https://api.github.com/app/installations/{ALICE_INSTALLATION}").mock(
            return_value=Response(200, json={"account": {"login": "alice"}})
        )

        async with _client() as http:
            await _signup(http, "alice@example.com")
            bob = await _signup(http, "bob@example.com")
            await _link("alice@example.com", ALICE_INSTALLATION)

            # Bob names Alice's account, which he can simply read off GitHub.
            response = await http.post(
                "/api/v1/github/installations/by-account",
                json={"account_login": "alice"},
                headers=bob,
            )

        assert response.status_code == 409

    async def test_it_requires_a_token(self):
        async with _client() as http:
            response = await http.post(
                "/api/v1/github/installations/by-account", json={"account_login": "alice"}
            )
        assert response.status_code == 401


class TestPrivateRepositoriesAreDeferred:
    def test_a_private_repository_is_refused_with_a_reason(self):
        with pytest.raises(RepositoryNotPermittedError) as excinfo:
            client.assert_analyzable({"full_name": "acme/secret", "private": True})
        # The message has to explain, because the user may well own the repo
        # and otherwise can't tell this from a bug.
        assert "public repositories only" in str(excinfo.value)

    def test_a_public_repository_is_allowed(self):
        client.assert_analyzable({"full_name": "acme/site", "private": False})


class TestWorkspaceIsolation:
    def test_a_workspace_is_confined_to_the_workspace_root(self, monkeypatch, tmp_path):
        monkeypatch.setattr(get_settings(), "workspace_root", str(tmp_path))
        path = workspace_for(uuid.uuid4(), uuid.uuid4())
        assert tmp_path.resolve() in path.parents

    def test_each_run_gets_its_own_directory(self, monkeypatch, tmp_path):
        """Two runs of one project must not share a checkout: a patch's line
        numbers belong to the commit its run analyzed."""
        monkeypatch.setattr(get_settings(), "workspace_root", str(tmp_path))
        project = uuid.uuid4()
        assert workspace_for(project, uuid.uuid4()) != workspace_for(project, uuid.uuid4())

    def test_reset_refuses_to_delete_outside_the_workspace_root(self, monkeypatch, tmp_path):
        monkeypatch.setattr(get_settings(), "workspace_root", str(tmp_path / "ws"))
        (tmp_path / "ws").mkdir()
        precious = tmp_path / "not-a-workspace"
        precious.mkdir()
        (precious / "keep.txt").write_text("important")

        with pytest.raises(SourceNotAccessibleError):
            reset(precious)
        assert (precious / "keep.txt").exists()


class TestUntrustedRepositoryContent:
    """A cloned repository is a third party's data, not our code."""

    def test_a_symlink_in_a_checkout_cannot_read_outside_it(self, tmp_path):
        checkout = tmp_path / "repo"
        checkout.mkdir()
        secret = tmp_path / "secret.css"
        secret.write_text("/* private */")
        (checkout / "leak.css").symlink_to(secret)
        (checkout / "real.css").write_text("p{}")

        paths, _ = list_source_files(checkout)

        # Following the link would put the target's contents in an LLM prompt.
        assert paths == ["real.css"]

    def test_only_ui_source_extensions_are_ever_listed(self, tmp_path):
        checkout = tmp_path / "repo"
        checkout.mkdir()
        for name in (".env", "id_rsa", "credentials.json", "secrets.yaml", "app.py"):
            (checkout / name).write_text("SECRET=1")
        (checkout / "page.html").write_text("<p>hi</p>")

        paths, _ = list_source_files(checkout)

        # An allowlist, so an unanticipated secret-bearing filename is
        # excluded by never having been included.
        assert paths == ["page.html"]

    def test_the_git_directory_is_never_listed(self, tmp_path):
        checkout = tmp_path / "repo"
        (checkout / ".git").mkdir(parents=True)
        (checkout / ".git" / "config.css").write_text("x{}")
        (checkout / "ok.css").write_text("y{}")

        assert list_source_files(checkout)[0] == ["ok.css"]

    def test_clone_disables_hooks_and_filters(self):
        """Repository-controlled hooks and LFS filters are code execution.

        Asserted against the source rather than by running git, because the
        point is that the flags are always passed, on every clone.
        """
        source = Path(client.__file__).read_text()
        assert "core.hooksPath=/dev/null" in source
        assert "filter.lfs.process=" in source


class TestTokensAreNotLeaked:
    def test_no_token_column_exists_on_any_model(self):
        """Tokens are minted per operation and dropped; nothing stores one."""
        columns = set(GitHubInstallation.__table__.columns.keys())
        assert not {c for c in columns if "token" in c or "secret" in c}

    async def test_a_failed_clone_never_puts_the_token_in_the_error(
        self, configured_app, monkeypatch, tmp_path
    ):
        """git writes the remote URL into its own stderr, and that URL
        carries the installation token — so a clone failure is the obvious
        way for one to escape into a log or an API response.

        Driven for real: a fake `git` that fails and echoes the URL it was
        given, exactly as the real one does.
        """
        secret = "ghs_SUPERSECRETTOKEN"

        async def fake_token(installation_id: int) -> str:
            return secret

        monkeypatch.setattr(client, "installation_token", fake_token)

        async def fake_exec(*args, **kwargs):
            class FailingGit:
                returncode = 1

                async def communicate(self):
                    # The real git prints the remote, token and all.
                    return b"", f"fatal: could not read from {args[-2]}".encode()

            return FailingGit()

        monkeypatch.setattr(client.asyncio, "create_subprocess_exec", fake_exec)

        with pytest.raises(GitHubAPIError) as excinfo:
            await client.clone(
                installation_id=1,
                full_name="acme/site",
                branch="main",
                destination=tmp_path / "checkout",
            )

        assert secret not in str(excinfo.value)
        assert "x-access-token" not in str(excinfo.value)


# A throwaway RSA key so JWT signing can be exercised without a real App.
_TEST_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEogIBAAKCAQEAwNveoVjZjfyQpUC/wss2QytlRYiGK9ZuH4FUUb6yfr8HRGa7
dDsCrMqLe8PTkd1bbj9TXCPy5eSaenRUt44j1aHN0N2gh0Lj8JmvYaEdhfhy+fyZ
QwG/qVezexuNXYwesftzaqlbdR/St6yLDsAaZvuIXnC1MAZyNk+6yHJEtZCKH5PY
C5kmeRcwXdglwb5cFJRaLynauC5rS0P6wpv/yEn46xws/UjXpxtKOIT0v6fHOIyM
3twvrqhabK2LIEwPsGo39boXp6E4SQDDtmsi6nhVuZtAeMRWoY3PTi7eNlkmkI3Y
RPBCZsDIjaByZINsYdwaIv2GW5GrPgZFyX8lvwIDAQABAoIBAAwz/V7NOJraNSwt
BX/ltths3wVq0ZPlh2X5RiS+rHGw/wc4zuSttTTKGNBV1ZsgXAraTpkrxyX9Hznf
XDBEegeoVisV/Z8sFYXhsO4RsUS1sfoXyHorxVJe88LhkpeC6GWk/lUXQ+u3KJtU
UMo3+pOzQm+OByZI9MzIomN7jisaJEceJLfAhrK4Af2VIyu/LTyXab7F5F77uvOL
PuXt5/AqzvYdSaHPiBWhhN1LerXm1ChnPJwVNNEG1DzqiWgSRo3uVrxKwUG2RgOv
9GP4wTUqalzJ0jtwGrVBgIkWGrx4xoLWWHTpqEGDPmY/9diSQVCp4z/kNfezxGcM
jHhi52kCgYEA4AAFUpxlvush5+yhyfFfWgHnnjjAp/pVfM9y+4QAe3hzR0P/iBNA
2jsB401XQCEj++PLSlQmwOJH7G498Y/QI37rwe2qxYAXKJ7z0OsRV+Z6NO6ogXSJ
5hKWAzvjbeukcEZXVbIayc3sYRqDNil73lerh2o8lf6B6vNFln96x2kCgYEA3Gj5
MnsXD7u4mJE0AeU8fVbCCD5qPSGACfLWXxicsq4E3OmS1soAdwHhNtbomr1Oqyno
aJ9HByyJ60ckNpPoyvUdVUis2jfIopKamituN0KyRqoIYfJwPfSkFA7W2Dnxxzf1
dzA0/mpK7aDrSWNjDSpEvrCY0hQBbsYEgipqxucCgYAvPvHgdcpkFXYmU9vgG0AQ
XPx8e93u0Dc9xweqkzIC2On/qxD3o4/3N6DzT3nKtfLAC1DykYNHBbND5BC+paWy
BvA1DCsL0zOPRs+ITjxvPNaj2X7DJ1B6rYrkjbovkhcx8zQyiAlsbTmhVZU9VEyj
Hfy46Ch1PqQqaTtRPfwomQKBgA9PGz/uXMOy/jdanoojKfhqtj9sVmS4lvQZ8dnZ
E8k1XREbCB/zF+UsNEBi3PUigPxShNn/dieBaHL3FgTUcS7np4ns6lSd20mvdR2Q
Nq+P6mIOHVbwR+uFun/KKBIMtEZqFJqatpOVPm8S5kTKqm6XqP61tWeiDBdtmZKQ
76mxAoGARZayFp9/UYONcfmh+mEW/217WcIN+AlMobhuAAYLL7IEDqrmrckkDxTS
OTxEnFTPLtI8ivd/nhZgN3ykRbEOrFu0D4bIdDQGM/3JL3Ku/eGOJ0J1TtxqwD6A
b/hiNcp5I6u20RNChITEqLIIb5icO7K7muPom3jjxjnlSfltJVI=
-----END RSA PRIVATE KEY-----
"""
