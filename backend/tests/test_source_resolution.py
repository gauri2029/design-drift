"""Which checkout a run reads from.

`_resolve_source` is the one place that knows a project can be backed by
GitHub or by a local `sources/` path. Everything downstream receives a
plain directory, so this function is what keeps the two providers from
leaking into the agents — and what keeps the pre-GitHub workflow working.

The GitHub branch is driven with a real local repository served over
`file://` rather than a mocked clone: the thing worth testing is that a
checkout actually lands on disk with the commit we recorded, which a stub
returning a fake SHA would assert nothing about.
"""

import asyncio
import subprocess
import uuid
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.models.project import Project
from app.services import design_analysis as service
from app.tools.repo_search import SourceNotAccessibleError

pytestmark = pytest.mark.anonymous

OWNER_ID = uuid.uuid4()


def _project(**overrides: object) -> Project:
    defaults = dict(
        id=uuid.uuid4(),
        owner_id=OWNER_ID,
        name="Marketing homepage",
        figma_file_key="abc",
        figma_node_id="1:23",
        target_url="https://example.com",
    )
    return Project(**{**defaults, **overrides})  # type: ignore[arg-type]


def _git_repo(path: Path, *, content: str = "<p>hello</p>") -> str:
    """A real one-commit repository. Returns its HEAD SHA."""
    path.mkdir(parents=True)
    (path / "index.html").write_text(content)
    run = lambda *args: subprocess.run(  # noqa: E731
        ["git", "-C", str(path), *args], check=True, capture_output=True
    )
    run("init", "-q", "-b", "main")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    run("add", ".")
    run("commit", "-qm", "initial")
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


class TestLocalSourcePath:
    async def test_a_source_path_resolves_under_the_source_root(self, monkeypatch, tmp_path):
        """The pre-GitHub workflow, unchanged."""
        (tmp_path / "marketing-site").mkdir()
        monkeypatch.setattr(get_settings(), "source_root", str(tmp_path))

        root, sha = await service._resolve_source(
            None,  # type: ignore[arg-type]  # the local branch never touches the db
            _project(source_path="marketing-site"),
            uuid.uuid4(),
        )

        assert root == (tmp_path / "marketing-site").resolve()
        # No commit: a hand-placed checkout has no revision to record.
        assert sha is None

    async def test_a_path_escaping_the_source_root_is_refused(self, monkeypatch, tmp_path):
        monkeypatch.setattr(get_settings(), "source_root", str(tmp_path / "sources"))
        (tmp_path / "sources").mkdir()
        (tmp_path / "secrets").mkdir()

        with pytest.raises(SourceNotAccessibleError):
            await service._resolve_source(
                None,  # type: ignore[arg-type]
                _project(source_path="../secrets"),
                uuid.uuid4(),
            )

    async def test_neither_provider_configured_is_not_an_error(self):
        """Every inspection agent still runs; the run just can't map
        findings onto files."""
        root, sha = await service._resolve_source(
            None,  # type: ignore[arg-type]
            _project(),
            uuid.uuid4(),
        )

        assert root is None and sha is None


class TestGitHubSource:
    @pytest.fixture
    def origin(self, tmp_path):
        """A real repository to clone, plus its HEAD."""
        path = tmp_path / "origin"
        return path, _git_repo(path)

    @pytest.fixture
    def github(self, monkeypatch, tmp_path, origin):
        """Point the GitHub client at the local repository.

        Only the two network boundaries are replaced — which installation
        can reach the repo, and what GitHub says about it. The clone itself
        runs for real against a file:// remote, so the workspace layout and
        the recorded SHA are the genuine ones.
        """
        path, _ = origin
        monkeypatch.setattr(get_settings(), "workspace_root", str(tmp_path / "ws"))

        async def fake_installation(db, user_id, full_name):
            return 42

        async def fake_get_repository(installation_id, full_name):
            return {"full_name": full_name, "private": False, "default_branch": "main"}

        async def fake_clone(*, installation_id, full_name, branch, destination):
            # Subprocesses are launched the way the real client does, so
            # the fake can't pass while an await-less implementation would
            # block the loop.
            destination.parent.mkdir(parents=True, exist_ok=True)
            clone = await asyncio.create_subprocess_exec(
                "git",
                "clone",
                "-q",
                "--branch",
                branch,
                str(path),
                str(destination),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert await clone.wait() == 0
            head = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                str(destination),
                "rev-parse",
                "HEAD",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await head.communicate()
            return stdout.decode().strip()

        monkeypatch.setattr(
            service.github_service, "installation_for_repository", fake_installation
        )
        monkeypatch.setattr(service.github_client, "get_repository", fake_get_repository)
        monkeypatch.setattr(service.github_client, "clone", fake_clone)

    async def test_the_repository_is_cloned_and_its_commit_recorded(self, github, origin):
        _, head = origin
        project = _project(github_repo_full_name="acme/site", github_branch="main")
        analysis_id = uuid.uuid4()

        root, sha = await service._resolve_source(None, project, analysis_id)  # type: ignore[arg-type]

        assert root is not None
        # A real checkout, not a path that merely looks right.
        assert (root / "index.html").read_text() == "<p>hello</p>"
        # The SHA is what makes a months-old finding's line numbers
        # interpretable; it has to be the commit actually analyzed.
        assert sha == head

    async def test_each_run_clones_into_its_own_workspace(self, github):
        """Two runs must not share a checkout: a patch's line numbers
        belong to the commit its own run analyzed."""
        project = _project(github_repo_full_name="acme/site", github_branch="main")

        first, _ = await service._resolve_source(None, project, uuid.uuid4())  # type: ignore[arg-type]
        second, _ = await service._resolve_source(None, project, uuid.uuid4())  # type: ignore[arg-type]

        assert first != second
        assert first is not None and second is not None
        assert first.is_dir() and second.is_dir()

    async def test_github_wins_when_a_source_path_is_also_set(self, github, monkeypatch, tmp_path):
        """ProjectCreate rejects both, but a row could still carry both —
        the resolution order must be unambiguous rather than accidental."""
        (tmp_path / "local").mkdir()
        monkeypatch.setattr(get_settings(), "source_root", str(tmp_path))
        project = _project(
            github_repo_full_name="acme/site", github_branch="main", source_path="local"
        )

        root, sha = await service._resolve_source(None, project, uuid.uuid4())  # type: ignore[arg-type]

        assert root is not None and (root / "index.html").exists()
        assert sha is not None

    async def test_a_repository_flipped_to_private_is_refused_at_run_time(
        self, github, monkeypatch
    ):
        """Checked again at every run, not only when the repo was chosen:
        a public repository can be made private afterwards."""
        from app.integrations.github.exceptions import RepositoryNotPermittedError

        async def now_private(installation_id, full_name):
            return {"full_name": full_name, "private": True, "default_branch": "main"}

        monkeypatch.setattr(service.github_client, "get_repository", now_private)
        project = _project(github_repo_full_name="acme/site", github_branch="main")

        with pytest.raises(RepositoryNotPermittedError):
            await service._resolve_source(None, project, uuid.uuid4())  # type: ignore[arg-type]

    async def test_a_stale_workspace_is_cleared_before_cloning(self, github, origin):
        """git refuses to clone into a non-empty directory, and a
        half-written checkout from an interrupted run must not be analyzed
        as though it were complete."""
        project = _project(github_repo_full_name="acme/site", github_branch="main")
        analysis_id = uuid.uuid4()

        from app.services.workspace import workspace_for

        stale = workspace_for(project.id, analysis_id)
        stale.mkdir(parents=True)
        (stale / "leftover.html").write_text("from an interrupted run")

        root, _ = await service._resolve_source(None, project, analysis_id)  # type: ignore[arg-type]

        assert root is not None
        assert not (root / "leftover.html").exists()
        assert (root / "index.html").exists()
