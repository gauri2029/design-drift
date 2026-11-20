"""Exporting a patch when the run's checkout is gone.

A run's checkout is scratch space: cleaned up by the pruner, lost on a
redeploy, absent from a restored database, and never present on the public
demo. The primary export diffs the on-disk backup against the patched file,
which is the truthful answer while that checkout exists — and nothing here
changes that path.

This covers the fallback, which rebuilds the diff from the proposal stored
on the run. The thing worth testing is not that it produces *a* string but
that it produces a diff `git apply` accepts: a hand-built hunk with the
wrong line counts or offsets parses fine and then fails at the moment the
user tries to use it, which is the worst place to find out.
"""

import subprocess
from pathlib import Path

import pytest

from app.models.design_analysis import DesignAnalysis
from app.services.patch_export import NothingToExportError, build_patch_from_proposal

ORIGINAL = """import React from 'react'

export function Hero() {
  return (
    <section className="hero">
      <h1>Recipes</h1>
    </section>
  )
}
"""


def _analysis(**overrides: object) -> DesignAnalysis:
    """A run whose proposal patches the Hero component."""
    defaults: dict[str, object] = {
        "model": "test",
        "result": {},
        "fix_proposal": {
            "summary": "Add the subtitle.",
            "fixes": [
                {
                    "finding_title": "Hero subtitle is missing",
                    "no_fix": False,
                    "confidence": "high",
                    "original_code_found": True,
                    "explanation": "Adds the subtitle.",
                    "patch": {
                        "file_path": "src/Hero.jsx",
                        # The <h1> sits on line 6 of ORIGINAL.
                        "line_start": 6,
                        "line_end": 6,
                        "original_code": "      <h1>Recipes</h1>",
                        "replacement_code": (
                            "      <h1>Recipes</h1>\n      <p>Everyday cooking</p>"
                        ),
                    },
                }
            ],
        },
        "fix_review": {
            "decisions": [
                {"finding_title": "Hero subtitle is missing", "decision": "approved", "note": None}
            ],
            "reviewed_at": "2026-11-01T10:00:00Z",
        },
    }
    defaults.update(overrides)
    return DesignAnalysis(**defaults)


def test_the_rebuilt_diff_is_one_git_applies(tmp_path: Path) -> None:
    """The property that matters: the export is usable, not merely produced.

    Runs the real `git apply` against a real repository. A diff with
    miscounted hunk lines passes every structural assertion and fails
    exactly here, which is where the user would have found it.
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Hero.jsx").write_text(ORIGINAL)

    run = lambda *args: subprocess.run(  # noqa: E731
        ["git", *args], cwd=repo, check=True, capture_output=True
    )
    run("init", "-q")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    run("add", ".")
    run("commit", "-qm", "initial")

    diff = build_patch_from_proposal(_analysis())
    (tmp_path / "change.patch").write_text(diff)

    # --unidiff-zero because these hunks carry no context: the proposal
    # stores the replaced span and not the lines around it. The exported
    # file states this command in its own preamble, and this test is what
    # keeps that instruction true.
    subprocess.run(
        ["git", "apply", "--check", "--unidiff-zero", str(tmp_path / "change.patch")],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "apply", "--unidiff-zero", str(tmp_path / "change.patch")],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    patched = (repo / "src" / "Hero.jsx").read_text()
    assert "<p>Everyday cooking</p>" in patched
    # The rest of the file survived: a wrong offset would have replaced the
    # import or the closing tags instead.
    assert patched.startswith("import React from 'react'")
    assert patched.rstrip().endswith("}")


def test_the_hunk_header_points_at_the_recorded_line() -> None:
    """Offsets come from the run, not from the fragment.

    difflib on two fragments would number the hunk from line 1, and
    `git apply` would then look for the change at the top of the file.
    """
    diff = build_patch_from_proposal(_analysis())

    assert "diff --git a/src/Hero.jsx b/src/Hero.jsx" in diff
    # Anchored at the line the run recorded, not at line 1 of the fragment.
    assert "@@ -6,1 +6,2 @@" in diff
    # The <h1> is unchanged, so it stays as a context line and only the
    # subtitle is added. Restating the <h1> as a -/+ pair would be a
    # needlessly fragile patch.
    assert " " + "      <h1>Recipes</h1>\n" in diff
    assert "+      <p>Everyday cooking</p>\n" in diff


def test_only_approved_patches_are_exported() -> None:
    """A rejected patch must not reach a ready-to-apply diff.

    The human approval step is the whole point of the workflow
    (docs/principles.md #5); exporting what a reviewer turned down would
    quietly undo it.
    """
    analysis = _analysis(
        fix_review={
            "decisions": [
                {
                    "finding_title": "Hero subtitle is missing",
                    "decision": "rejected",
                    "note": "not now",
                }
            ],
            "reviewed_at": "2026-11-01T10:00:00Z",
        }
    )

    with pytest.raises(NothingToExportError):
        build_patch_from_proposal(analysis)


def test_an_unreviewed_run_exports_nothing_misleading() -> None:
    """With no review recorded, there is no approval to honour.

    Exported anyway rather than refused: `fix_review` is null on every run
    until someone looks at it, and the alternative is that the diff is
    unavailable until a review happens. What must not happen is a
    *rejected* patch being included, which the test above covers.
    """
    diff = build_patch_from_proposal(_analysis(fix_review=None))
    assert "<p>Everyday cooking</p>" in diff


def test_a_run_with_no_proposal_is_refused() -> None:
    with pytest.raises(NothingToExportError):
        build_patch_from_proposal(_analysis(fix_proposal=None))


def test_a_no_fix_entry_is_skipped() -> None:
    """`no_fix` means the agent declined to patch that finding."""
    analysis = _analysis(
        fix_proposal={
            "summary": "Nothing safe to change.",
            "fixes": [
                {
                    "finding_title": "Hero subtitle is missing",
                    "no_fix": True,
                    "patch": None,
                    "explanation": "Could not locate it confidently.",
                    "confidence": "low",
                    "original_code_found": False,
                }
            ],
        }
    )

    with pytest.raises(NothingToExportError):
        build_patch_from_proposal(analysis)


def test_the_export_states_the_command_it_needs() -> None:
    """The download outlives the page it came from.

    A zero-context diff fails under a plain `git apply`, so the file says
    which flag it needs. The assertion pairs with the apply test above: if
    the diff shape ever changes so that the flag is wrong, one of the two
    fails.
    """
    diff = build_patch_from_proposal(_analysis())

    assert diff.startswith("# Design Drift:")
    assert "git apply --unidiff-zero" in diff
    # git ignores '#' lines, so the preamble cannot break the patch.
    preamble = diff.split("diff --git", 1)[0]
    assert all(line.startswith("#") for line in preamble.splitlines() if line)
