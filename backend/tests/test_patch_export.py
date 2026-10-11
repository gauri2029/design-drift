"""The downloadable patch.

The export exists so an approved change can reach a repository without
Design Drift ever writing to it: the user runs `git apply` themselves.
"""

import uuid

import pytest

from app.models.design_analysis import DesignAnalysis
from app.services.patch_export import NothingToExportError, build_patch
from app.tools.repo_search import BACKUP_DIRECTORY


def _analysis(fixes: list[dict]) -> DesignAnalysis:
    return DesignAnalysis(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        model="test",
        result={},
        fix_application={"applied_at": "2026-01-01T00:00:00Z", "fixes": fixes},
    )


def _checkout(tmp_path, *, before: str, after: str, name: str = "index.html"):
    """A checkout as apply_patch leaves it: file patched, original in backups."""
    backup_dir = tmp_path / BACKUP_DIRECTORY / "run"
    backup_dir.mkdir(parents=True)
    (backup_dir / name).write_text(before)
    (tmp_path / name).write_text(after)
    return f"{BACKUP_DIRECTORY}/run/{name}"


def test_the_patch_reflects_what_was_written(tmp_path):
    backup = _checkout(tmp_path, before="<html>\n", after='<html lang="en">\n')
    analysis = _analysis(
        [
            {
                "finding_title": "html-has-lang",
                "file_path": "index.html",
                "applied": True,
                "backup_path": backup,
            }
        ]
    )

    patch = build_patch(analysis, tmp_path)

    # a/ and b/ prefixes are what `git apply -p1` expects.
    assert "--- a/index.html" in patch
    assert "+++ b/index.html" in patch
    assert "-<html>" in patch
    assert '+<html lang="en">' in patch


def test_a_skipped_patch_is_not_in_the_export(tmp_path):
    """What's exported is what landed, not what was proposed."""
    backup = _checkout(tmp_path, before="<html>\n", after='<html lang="en">\n')
    analysis = _analysis(
        [
            {
                "finding_title": "landed",
                "file_path": "index.html",
                "applied": True,
                "backup_path": backup,
            },
            # Didn't fit the file any more, so it was never written.
            {
                "finding_title": "skipped",
                "file_path": "other.html",
                "applied": False,
                "reason": "the original code was not found",
                "backup_path": None,
            },
        ]
    )

    patch = build_patch(analysis, tmp_path)

    assert "index.html" in patch
    assert "other.html" not in patch


def test_a_run_that_wrote_nothing_says_so(tmp_path):
    analysis = _analysis(
        [{"finding_title": "x", "file_path": "a.html", "applied": False, "backup_path": None}]
    )

    with pytest.raises(NothingToExportError):
        build_patch(analysis, tmp_path)


def test_a_file_whose_content_is_unchanged_is_omitted(tmp_path):
    """A re-apply of an already-present change produces an empty diff."""
    backup = _checkout(tmp_path, before="<html>\n", after="<html>\n")
    analysis = _analysis(
        [{"finding_title": "x", "file_path": "index.html", "applied": True, "backup_path": backup}]
    )

    with pytest.raises(NothingToExportError):
        build_patch(analysis, tmp_path)
