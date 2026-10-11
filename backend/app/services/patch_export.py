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
