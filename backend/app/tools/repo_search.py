"""Deterministic read-only access to a target app's source checkout — the
first entry in `app/tools/` (agent tool implementations; see
docs/architecture.md's backend structure).

No LLM here: enumerating files, and finding which lines contain a given
anchor, are things the filesystem and string matching answer exactly
(docs/principles.md #2). Deciding which of the ranked candidates is
actually the cause is the judgment call, and that belongs to the Code
Analysis Agent that calls this.

Read-only by construction — nothing in this module writes, moves, or
deletes, and the Fix Agent that calls it only proposes patches as text.
Writing an approved patch back is a separate, explicitly human-gated step
in app.tools.apply_patch (docs/principles.md #5).
"""

from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from app.core.config import get_settings
from app.tools.anchors import Anchor


class SourceNotAccessibleError(Exception):
    """Raised when a project's configured source path can't be used."""


# Allowlist, not a blocklist. Two reasons: the Code Analysis Agent only
# cares about files that can contain UI code, and an allowlist fails
# closed — `.env`, `id_rsa`, `credentials.json` and anything else
# unanticipated are excluded because they were never included, rather than
# because someone remembered to name them.
SOURCE_EXTENSIONS = frozenset(
    {
        ".astro",
        ".css",
        ".html",
        ".js",
        ".jsx",
        ".less",
        ".sass",
        ".scss",
        ".svelte",
        ".ts",
        ".tsx",
        ".vue",
    }
)

# Directories that are never a project's own source: dependency trees,
# build output, VCS internals. Skipping them keeps the listing meaningful
# (and small) rather than drowning real files in node_modules.
IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".next",
        ".nuxt",
        ".svelte-kit",
        ".turbo",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "out",
        "target",
        "vendor",
    }
)

# A single LLM call can't usefully reason over an unbounded file list, and
# an unbounded listing is also an unbounded prompt (cost, and eventually a
# context-limit error). Truncation is surfaced to the caller rather than
# hidden — see list_source_files' return contract.
MAX_FILES = 400

# Skip files larger than this when reading contents. Mostly this catches
# committed bundles and minified vendor blobs — reading them is slow, they
# blow up any prompt they reach, and they're never where a human would fix
# a design bug.
MAX_FILE_BYTES = 256_000

# How many ranked files get snippets built and handed to the model. Kept
# modest because the snippets below are large; the low-scoring tail of the
# ranking rarely earns its share of the prompt.
MAX_CANDIDATES = 5

# Context around the best-matching line. Deliberately asymmetric: markup
# nests *downward* from an opening tag or a heading, so what a finding
# needs is almost always below the match, not above it. A symmetric
# window centred on a section's heading shows the heading and the text
# before it, and stops right before the list the question was about.
SNIPPET_LINES_BEFORE = 8
SNIPPET_LINES_AFTER = 40

# Long lines are almost always minified or generated; truncate rather than
# let one line dominate a snippet.
MAX_LINE_CHARS = 300

# An anchor appearing in more than this many files isn't locating
# anything — it's boilerplate for this codebase (a wrapper class, a
# framework import). Dropping it is a document-frequency filter, and it
# adapts to the repo at hand instead of relying on a guessed stoplist (see
# app.tools.anchors._GENERIC_TOKENS, which is only a cheap first pass).
MAX_ANCHOR_FILE_MATCHES = 40

# path -> lines, read once so per-finding searches don't re-read the repo.
SourceCorpus = dict[str, list[str]]


class CandidateMatch(BaseModel):
    """One file that contains anchor evidence, with the strongest region."""

    path: str
    score: int
    matched_anchors: list[str]
    # 1-indexed and inclusive, matching how editors and humans count.
    line_start: int
    line_end: int
    snippet: str


def resolve_source_root(source_path: str) -> Path:
    """Resolve a project's `source_path` against the configured source root.

    The returned path is guaranteed to be an existing directory *inside*
    `settings.source_root`. Both sides are `.resolve()`d first, so `..`
    segments and symlinks that point outside the root are caught rather
    than followed — see Settings.source_root on why that containment
    matters here specifically.
    """
    root = Path(get_settings().source_root).resolve()
    candidate = (root / source_path).resolve()

    if candidate != root and root not in candidate.parents:
        raise SourceNotAccessibleError(
            f"source path {source_path!r} resolves outside the configured source root"
        )
    if not candidate.is_dir():
        raise SourceNotAccessibleError(
            f"source path {source_path!r} is not an existing directory under the source root"
        )
    return candidate


def list_source_files(root: Path) -> tuple[list[str], bool]:
    """List candidate UI source files under `root`, newest-agnostic and sorted.

    Returns `(paths, truncated)` — paths are relative to `root` (so nothing
    about the host's directory layout leaks into a prompt), sorted for
    deterministic output, and `truncated` says whether MAX_FILES cut the
    listing short so the caller can tell the model its view is partial.
    """
    paths: list[str] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_DIRECTORIES for part in relative.parts):
            continue
        paths.append(relative.as_posix())

    truncated = len(paths) > MAX_FILES
    return paths[:MAX_FILES], truncated


def load_source_corpus(root: Path) -> SourceCorpus:
    """Read every listed source file once, into `{relative path: lines}`.

    Files that are too large, or that aren't valid UTF-8 text, are skipped
    rather than partially decoded — a binary blob with a source extension
    has nothing to contribute to an anchor search.
    """
    corpus: SourceCorpus = {}
    paths, _ = list_source_files(root)

    for relative in paths:
        text = _read_text(root / relative)
        if text is not None:
            corpus[relative] = text.splitlines()
    return corpus


def search_corpus(corpus: SourceCorpus, anchors: Sequence[Anchor]) -> list[CandidateMatch]:
    """Rank files by how much anchor evidence they contain.

    A file's score is the summed weight of the *distinct* anchors it
    matches, so a file hitting an id and a matching label outranks one
    that repeats a single class name a hundred times. Ties break on path,
    to keep output deterministic.
    """
    if not anchors:
        return []

    # Pass 1: which lines each anchor hits, per file.
    hits: dict[str, dict[int, list[int]]] = {}
    document_frequency: Counter[int] = Counter()

    for path, lines in corpus.items():
        per_anchor: dict[int, list[int]] = {}
        for index, anchor in enumerate(anchors):
            matched = [number for number, line in enumerate(lines, 1) if anchor.matches(line)]
            if matched:
                per_anchor[index] = matched
                document_frequency[index] += 1
        if per_anchor:
            hits[path] = per_anchor

    # Pass 2: drop anchors that matched too much to discriminate, then score.
    too_common = {
        index for index, count in document_frequency.items() if count > MAX_ANCHOR_FILE_MATCHES
    }

    candidates: list[CandidateMatch] = []
    for path, per_anchor in hits.items():
        kept = {index: lines for index, lines in per_anchor.items() if index not in too_common}
        if not kept:
            continue

        line_start, line_end = _best_region(kept, len(corpus[path]))
        candidates.append(
            CandidateMatch(
                path=path,
                score=sum(anchors[index].weight for index in kept),
                matched_anchors=sorted(anchors[index].value for index in kept),
                line_start=line_start,
                line_end=line_end,
                snippet=_snippet(corpus[path], line_start, line_end),
            )
        )

    candidates.sort(key=lambda candidate: (-candidate.score, candidate.path))
    return candidates[:MAX_CANDIDATES]


def _best_region(matches: dict[int, list[int]], total_lines: int) -> tuple[int, int]:
    """Centre the snippet on the line carrying the most distinct anchors."""
    per_line: Counter[int] = Counter()
    for lines in matches.values():
        for number in set(lines):
            per_line[number] += 1

    # Most anchors wins; earliest line breaks ties, so output is stable.
    best_line = min(per_line, key=lambda number: (-per_line[number], number))
    return (
        max(1, best_line - SNIPPET_LINES_BEFORE),
        min(total_lines, best_line + SNIPPET_LINES_AFTER),
    )


def _snippet(lines: list[str], line_start: int, line_end: int) -> str:
    return "\n".join(
        f"{number}: {lines[number - 1][:MAX_LINE_CHARS]}"
        for number in range(line_start, line_end + 1)
    )


def _read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
