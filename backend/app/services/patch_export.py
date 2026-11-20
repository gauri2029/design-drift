"""A unified diff of what an approved run actually wrote.

Built from the backups apply_patch keeps rather than from the proposed
patches: what the user downloads should be the change that landed, which
can differ from what was proposed (a patch that no longer fitted is
skipped, and one already present is a no-op).

Read-only, and nothing is sent to GitHub. The export exists so a user can
take the result to their own repository themselves — `git apply`, a branch,
a PR they open — which keeps every write on their side of the line
(docs/principles.md #5).
"""

import difflib
from pathlib import Path

from app.models.design_analysis import DesignAnalysis
from app.tools.repo_search import BACKUP_DIRECTORY


class NothingToExportError(Exception):
    """No patch from this run was actually written."""


def build_patch_from_proposal(analysis: DesignAnalysis) -> str:
    """A diff rebuilt from the stored proposal, with no checkout needed.

    The primary path (`build_patch`) diffs the backup against the patched
    file on disk, which is the truthful answer when the checkout is still
    there: it shows the change that actually landed. But a run's checkout
    is scratch space, so it is gone on a redeploy, on a cloned database,
    and on the public demo — and refusing to export then means the most
    useful artifact of a finished run becomes unreachable the moment the
    workspace is cleaned up.

    The proposal itself carries both sides of every patch
    (`original_code` and `replacement_code`, each verified against the real
    file at propose time — see app.agents.fix), so the diff can be
    reconstructed from the row. Line numbers come from the run as well,
    which keeps the hunk headers pointing where the patch was written.

    What this cannot do is notice that the file has changed since. That is
    exactly why it is the fallback and not the default.
    """
    proposal = analysis.fix_proposal or {}
    raw_fixes = proposal.get("fixes")
    fixes: list[object] = raw_fixes if isinstance(raw_fixes, list) else []

    # Only patches a human approved. An unreviewed or rejected proposal is
    # not something to hand someone as a ready-to-apply diff.
    approved = _approved_titles(analysis)

    chunks: list[str] = []
    for fix in fixes:
        if not isinstance(fix, dict) or fix.get("no_fix"):
            continue
        if approved is not None and fix.get("finding_title") not in approved:
            continue
        patch = fix.get("patch")
        if not isinstance(patch, dict):
            continue

        file_path = patch.get("file_path")
        before = patch.get("original_code")
        after = patch.get("replacement_code")
        if not isinstance(file_path, str) or not isinstance(before, str):
            continue
        if not isinstance(after, str) or before == after:
            continue

        start = patch.get("line_start")
        start_line = start if isinstance(start, int) and start > 0 else 1

        chunks.append(_hunk(file_path, before, after, start_line))

    if not chunks:
        raise NothingToExportError(
            "this run has no approved patch to export, so there is nothing to build a diff from"
        )

    # The hunks below carry no surrounding context (see _hunk), so `git
    # apply` needs --unidiff-zero. Saying so in the file itself rather than
    # only in the UI: the download outlives the page it came from, and
    # someone opening it a week later should find the command in it.
    #
    # Lines starting with '#' are ignored by git apply, so this is safe to
    # prepend to a real patch.
    preamble = (
        "# Design Drift: patches rebuilt from this run's stored proposal.\n"
        "#\n"
        "# Apply with:\n"
        "#     git apply --unidiff-zero design-drift.patch\n"
        "#\n"
        "# The --unidiff-zero flag is required because these hunks have no\n"
        "# surrounding context lines. Review the change before applying it,\n"
        "# and check the line numbers still match your current file.\n"
        "#\n"
    )
    return preamble + "".join(chunks)


def _approved_titles(analysis: DesignAnalysis) -> set[str] | None:
    """Titles the reviewer approved, or None when there is no review.

    None rather than an empty set, so an unreviewed run is distinguishable
    from one where everything was rejected: the caller treats the first as
    "no filter recorded" and the second as "nothing approved".
    """
    review = analysis.fix_review
    if not review:
        return None
    raw = review.get("decisions")
    if not isinstance(raw, list):
        return None
    return {
        decision["finding_title"]
        for decision in raw
        if isinstance(decision, dict)
        and decision.get("decision") == "approved"
        and isinstance(decision.get("finding_title"), str)
    }


def _hunk(file_path: str, before: str, after: str, start_line: int) -> str:
    """One unified-diff hunk for a replaced span of a file.

    Written by hand rather than via difflib because the two sides here are
    fragments, not whole files: difflib numbers a hunk from line 1 of what
    it was given, and `git apply` would then look for the change at the top
    of the file.

    Line-by-line rather than removing the whole fragment and adding the
    whole replacement. A replacement usually keeps most of the original
    (the subtitle case adds one line and touches nothing else), so this
    keeps the diff readable: a reviewer sees the one line that changed
    rather than the whole span restated as a -/+ pair.

    These hunks carry no surrounding context, because the proposal stores
    only the replaced span and not the lines around it. That makes the
    output a *zero-context* diff, which `git apply` accepts only with
    `--unidiff-zero` — so the export says so, in a comment at the top of
    the file (see `build_patch_from_proposal`). Zero context is also why
    this is the fallback: with the checkout present, `build_patch` diffs
    whole files and produces an ordinary patch that needs no flag.
    """
    lines = _opcodes_to_lines(before.splitlines(), after.splitlines())

    body = "".join(f"{code}{line}\n" for code, line in lines)

    # Counts must match the lines actually emitted: context and removals on
    # the left, context and additions on the right. git validates these.
    old_count = sum(1 for code, _ in lines if code in " -")
    new_count = sum(1 for code, _ in lines if code in " +")

    return (
        f"diff --git a/{file_path} b/{file_path}\n"
        f"--- a/{file_path}\n"
        f"+++ b/{file_path}\n"
        f"@@ -{start_line},{old_count} +{start_line},{new_count} @@\n"
    ) + body


def _opcodes_to_lines(
    before_lines: list[str], after_lines: list[str]
) -> list[tuple[str, str]]:
    """The fragment pair as (marker, line) pairs: ' ', '-' or '+'."""
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines, autojunk=False)
    lines: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            lines += [(" ", line) for line in before_lines[i1:i2]]
        else:
            # 'replace' is a delete plus an insert, in that order, which is
            # what unified diff expects.
            lines += [("-", line) for line in before_lines[i1:i2]]
            lines += [("+", line) for line in after_lines[j1:j2]]
    return lines



def build_patch(analysis: DesignAnalysis, source_root: Path) -> str:
    """A `git apply`-able diff of every file this run modified."""
    application = analysis.fix_application or {}
    # fix_application is a JSONB column typed as dict[str, object], so the
    # nested list needs narrowing before it can be iterated.
    raw_fixes = application.get("fixes")
    fixes: list[object] = raw_fixes if isinstance(raw_fixes, list) else []

    chunks: list[str] = []
    for fix in fixes:
        if not isinstance(fix, dict) or not fix.get("applied"):
            continue
        file_path = fix.get("file_path")
        backup_path = fix.get("backup_path")
        if not isinstance(file_path, str) or not isinstance(backup_path, str):
            continue

        before = _read(source_root / backup_path)
        after = _read(source_root / file_path)
        if before is None or after is None or before == after:
            continue

        chunks.append(
            "".join(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    after.splitlines(keepends=True),
                    # a/ and b/ prefixes are what `git apply -p1` expects.
                    fromfile=f"a/{file_path}",
                    tofile=f"b/{file_path}",
                )
            )
        )

    if not chunks:
        raise NothingToExportError(
            "no approved patch from this run was written to a file, so there is nothing to export"
        )
    return "".join(chunks)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def backup_directory_name() -> str:
    return BACKUP_DIRECTORY
