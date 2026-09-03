"""The one place in this codebase that writes to a user's source checkout.

Everything else under `app/tools/` is read-only by construction. This
module is the exception, and it exists only downstream of an explicit
human approval (docs/principles.md #5): the Fix Agent proposes, a person
approves, and then this splices the approved text in. It writes files and
nothing more — it never runs `git`, never stages, never commits, never
pushes. The checkout's own version control is the user's undo.

No LLM here either (docs/principles.md #2). Given a patch and a file,
"does this code still say what the patch claims" and "which lines does the
replacement go on" are exact questions, so they're answered exactly, and a
patch that no longer fits is skipped and reported rather than forced.
"""

from pathlib import Path

from pydantic import BaseModel

from app.agents.types import Patch
from app.tools.repo_search import SOURCE_EXTENSIONS, SourceNotAccessibleError


class PatchOutcome(BaseModel):
    """What happened to one patch. Applied is the good case; the rest are
    all "we declined to write", each with a distinguishable reason so the
    UI can say why rather than just failing."""

    applied: bool
    # Machine-readable so the frontend can style it; the human-facing
    # sentence is built from this rather than parsed out of prose.
    reason: str | None = None


def resolve_within(root: Path, file_path: str) -> Path:
    """A patch's `file_path` as a real path inside `root`.

    Same containment rule as repo_search.resolve_source_root, for the same
    reason but with more at stake: this path gets *written* to. A patch's
    file_path came from an LLM, so `../../.ssh/authorized_keys` is a shape
    the input can take and has to be refused, not merely unlikely.
    """
    target = (root / file_path).resolve()
    if root.resolve() not in target.parents:
        raise SourceNotAccessibleError(
            f"patch target {file_path!r} resolves outside the source checkout"
        )
    # The same allowlist the search side uses. A patch can only touch a
    # file the Code Analysis pass could have read in the first place.
    if target.suffix.lower() not in SOURCE_EXTENSIONS:
        raise SourceNotAccessibleError(f"patch target {file_path!r} is not an editable source file")
    return target


def _normalize(lines: list[str]) -> str:
    """Compare on stripped, non-blank lines.

    A patch's `original_code` is the model's transcription of a snippet, so
    trailing whitespace and blank-line differences are noise. Indentation
    is not compared for the same reason — but it's also not *rewritten*:
    the replacement is written exactly as proposed.
    """
    return "\n".join(line.strip() for line in lines if line.strip())


def _locate(lines: list[str], patch: Patch) -> tuple[int, int] | None:
    """The 0-indexed half-open slice `patch.original_code` occupies, if any.

    The patch's own line numbers are tried first, since they came from the
    snippet the model was shown. They can be stale — the file may have
    changed since the run, or an earlier patch may have shifted it — so
    fall back to searching the file for the same block. That fallback
    requires exactly one occurrence: two matching regions means we can't
    tell which one the reviewer approved, which is a reason to stop rather
    than to guess.
    """
    wanted = _normalize(patch.original_code.splitlines())
    if not wanted:
        return None

    start, end = patch.line_start - 1, patch.line_end
    if 0 <= start < end <= len(lines) and _normalize(lines[start:end]) == wanted:
        return start, end

    span = end - start
    matches = [
        (index, index + span)
        for index in range(0, max(len(lines) - span + 1, 0))
        if _normalize(lines[index : index + span]) == wanted
    ]
    return matches[0] if len(matches) == 1 else None


def apply_patches(root: Path, patches: list[tuple[str, Patch]]) -> dict[str, PatchOutcome]:
    """Apply approved patches to files under `root`, keyed by finding title.

    Every patch is re-checked against the file as it is *now*, not as it
    was during the run: a reviewer may have approved hours ago, and the
    file is theirs to edit in the meantime. A patch whose original code
    has since moved or changed is skipped, not forced.

    Patches to the same file are applied bottom-up so that splicing one
    doesn't shift the line numbers of the ones above it, and each file is
    written once, at the end — a file with any failing patch still gets its
    other, valid patches, but a file is never left half-written by an
    exception mid-loop.
    """
    outcomes: dict[str, PatchOutcome] = {}
    by_file: dict[str, list[tuple[str, Patch]]] = {}

    for title, patch in patches:
        try:
            resolve_within(root, patch.file_path)
        except SourceNotAccessibleError as exc:
            outcomes[title] = PatchOutcome(applied=False, reason=str(exc))
            continue
        by_file.setdefault(patch.file_path, []).append((title, patch))

    for file_path, file_patches in by_file.items():
        target = resolve_within(root, file_path)
        if not target.is_file():
            for title, _ in file_patches:
                outcomes[title] = PatchOutcome(applied=False, reason="file no longer exists")
            continue

        original = target.read_text(encoding="utf-8")
        lines = original.splitlines()
        changed = False

        for title, patch in sorted(file_patches, key=lambda item: item[1].line_start, reverse=True):
            span = _locate(lines, patch)
            if span is None:
                outcomes[title] = PatchOutcome(
                    applied=False,
                    reason="the code this patch replaces is no longer in the file at that place",
                )
                continue
            start, end = span
            lines[start:end] = patch.replacement_code.splitlines()
            outcomes[title] = PatchOutcome(applied=True)
            changed = True

        if changed:
            # Preserve whether the file ended with a newline. Flipping that
            # shows up as a whole-file diff in the user's next `git diff`,
            # which buries the change they actually approved.
            suffix = "\n" if original.endswith("\n") else ""
            target.write_text("\n".join(lines) + suffix, encoding="utf-8")

    return outcomes
