"""Pruning unreferenced artifacts.

The risk here is asymmetric: failing to delete litter wastes disk, while
deleting a live artifact loses a screenshot a user can still open. So the
tests care most about what must *survive*.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.design_analysis import DesignAnalysis
from app.models.project import Project
from app.models.user import User
from app.tools import prune_storage

pytestmark = pytest.mark.anonymous


@pytest.fixture(autouse=True)
async def _clean_up():
    yield
    async with async_session_factory() as session:
        await session.execute(delete(Project))
        await session.execute(delete(User))
        await session.commit()


@pytest.fixture
async def live_project(monkeypatch, tmp_path):
    """A project and one analysis, with their directories on disk."""
    monkeypatch.setattr(get_settings(), "storage_root", str(tmp_path))
    async with async_session_factory() as session:
        user = User(email="o@example.com", name="O", password_hash="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        project = Project(
            owner_id=user.id,
            name="p",
            figma_file_key="k",
            figma_node_id="1:1",
            target_url="https://example.com",
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)

        analysis = DesignAnalysis(project_id=project.id, model="m", result={})
        session.add(analysis)
        await session.commit()
        await session.refresh(analysis)

    for group, ident in (("figma", project.id), ("design-analyses", analysis.id)):
        d = tmp_path / group / str(ident)
        d.mkdir(parents=True)
        (d / "preview.png").write_bytes(b"png")
    return tmp_path, project, analysis


def _orphan(root, group: str) -> "object":
    d = root / group / str(uuid.uuid4())
    d.mkdir(parents=True)
    (d / "preview.png").write_bytes(b"png" * 100)
    return d


async def test_a_dry_run_deletes_nothing(live_project, capsys):
    root, project, _ = live_project
    orphan = _orphan(root, "figma")

    prune_storage.prune(await prune_storage._referenced_ids(), delete=False)

    # The default has to be safe: this is a command someone runs to find
    # out what it would do.
    assert orphan.exists()
    assert "nothing deleted" in capsys.readouterr().out


async def test_referenced_artifacts_survive(live_project):
    root, project, analysis = live_project
    orphan = _orphan(root, "design-analyses")
    prune_storage.prune(await prune_storage._referenced_ids(), delete=True)

    assert not orphan.exists()
    # The whole point: a live project's screenshots are still openable.
    assert (root / "figma" / str(project.id) / "preview.png").exists()
    assert (root / "design-analyses" / str(analysis.id) / "preview.png").exists()


async def test_a_directory_that_is_not_an_id_is_left_alone(live_project):
    """Anything a human put there is not ours to judge."""
    root, _, _ = live_project
    manual = root / "figma" / "keep-these-notes"
    manual.mkdir(parents=True)
    (manual / "README.txt").write_text("not an artifact")
    prune_storage.prune(await prune_storage._referenced_ids(), delete=True)

    assert manual.exists()


async def test_it_reports_when_there_is_nothing_to_do(live_project, capsys):
    prune_storage.prune(await prune_storage._referenced_ids(), delete=False)

    assert "no orphaned artifacts" in capsys.readouterr().out
