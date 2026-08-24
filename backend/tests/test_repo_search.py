"""Unit tests for app.tools.repo_search — real files on disk under tmp_path,
no mocking of the filesystem (the whole point of this module is what it
does with real paths, symlinks included).
"""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.tools.anchors import Anchor, AnchorKind
from app.tools.repo_search import (
    MAX_ANCHOR_FILE_MATCHES,
    MAX_CANDIDATES,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_LINE_CHARS,
    SourceNotAccessibleError,
    list_source_files,
    load_source_corpus,
    resolve_source_root,
    search_corpus,
)


@pytest.fixture
def source_root(tmp_path: Path, monkeypatch) -> Path:
    """Point Settings.source_root at a tmp dir, and return it resolved.

    Resolved because macOS's /var -> /private/var symlink otherwise makes
    the configured root and the resolved candidate differ, which is
    exactly the kind of mismatch resolve_source_root has to handle.
    """
    root = tmp_path / "sources"
    root.mkdir()
    monkeypatch.setattr(get_settings(), "source_root", str(root))
    return root.resolve()


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_resolves_a_path_inside_the_configured_root(source_root: Path) -> None:
    (source_root / "my-app").mkdir()

    assert resolve_source_root("my-app") == source_root / "my-app"


def test_rejects_a_path_escaping_the_root_with_dotdot(source_root: Path) -> None:
    # The directory genuinely exists — this must be refused for being
    # outside the root, not merely for being missing.
    outside = source_root.parent / "outside"
    outside.mkdir()

    with pytest.raises(SourceNotAccessibleError, match="outside"):
        resolve_source_root("../outside")


def test_rejects_an_absolute_path(source_root: Path) -> None:
    outside = source_root.parent / "elsewhere"
    outside.mkdir()

    # Path("/root") / "/abs" == Path("/abs") — an absolute segment wins,
    # so this would silently escape without the containment check.
    with pytest.raises(SourceNotAccessibleError, match="outside"):
        resolve_source_root(str(outside))


def test_rejects_a_symlink_pointing_outside_the_root(source_root: Path) -> None:
    outside = source_root.parent / "outside-target"
    outside.mkdir()
    (source_root / "sneaky").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SourceNotAccessibleError, match="outside"):
        resolve_source_root("sneaky")


def test_rejects_a_path_that_is_not_a_directory(source_root: Path) -> None:
    _write(source_root / "not-a-dir.txt")

    with pytest.raises(SourceNotAccessibleError, match="not an existing directory"):
        resolve_source_root("not-a-dir.txt")


def test_rejects_a_missing_path(source_root: Path) -> None:
    with pytest.raises(SourceNotAccessibleError, match="not an existing directory"):
        resolve_source_root("nope")


def test_lists_source_files_relative_and_sorted(tmp_path: Path) -> None:
    root = tmp_path / "app"
    _write(root / "src" / "Button.tsx")
    _write(root / "src" / "App.tsx")
    _write(root / "styles.css")

    paths, truncated = list_source_files(root)

    assert paths == ["src/App.tsx", "src/Button.tsx", "styles.css"]
    assert truncated is False


def test_excludes_files_outside_the_extension_allowlist(tmp_path: Path) -> None:
    root = tmp_path / "app"
    _write(root / "Button.tsx")
    # An allowlist means secrets are excluded by never being included —
    # nobody has to remember to name them (see SOURCE_EXTENSIONS).
    _write(root / ".env", "ANTHROPIC_API_KEY=sk-secret")
    _write(root / "id_rsa", "PRIVATE KEY")
    _write(root / "README.md")
    _write(root / "logo.png")

    paths, _ = list_source_files(root)

    assert paths == ["Button.tsx"]


def test_skips_ignored_directories_at_any_depth(tmp_path: Path) -> None:
    root = tmp_path / "app"
    _write(root / "src" / "App.tsx")
    _write(root / "node_modules" / "react" / "index.js")
    _write(root / "dist" / "bundle.js")
    _write(root / "packages" / "ui" / "node_modules" / "dep" / "index.js")

    paths, _ = list_source_files(root)

    assert paths == ["src/App.tsx"]


def test_truncates_at_max_files_and_reports_it(tmp_path: Path) -> None:
    root = tmp_path / "app"
    for index in range(MAX_FILES + 10):
        _write(root / f"file{index:04d}.ts")

    paths, truncated = list_source_files(root)

    assert len(paths) == MAX_FILES
    assert truncated is True


def test_reports_not_truncated_exactly_at_the_limit(tmp_path: Path) -> None:
    root = tmp_path / "app"
    for index in range(MAX_FILES):
        _write(root / f"file{index:04d}.ts")

    paths, truncated = list_source_files(root)

    assert len(paths) == MAX_FILES
    assert truncated is False


def test_empty_directory_lists_nothing(tmp_path: Path) -> None:
    root = tmp_path / "app"
    root.mkdir()

    assert list_source_files(root) == ([], False)


# --- content search -------------------------------------------------------


def _anchor(kind: AnchorKind, value: str) -> Anchor:
    return Anchor(kind=kind, value=value)


def test_corpus_reads_only_allowlisted_files(tmp_path: Path) -> None:
    root = tmp_path / "app"
    _write(root / "Button.tsx", "export const Button = () => null")
    _write(root / ".env", "ANTHROPIC_API_KEY=sk-secret")
    _write(root / "id_rsa", "PRIVATE KEY")

    corpus = load_source_corpus(root)

    # Contents of disallowed files never even enter memory, let alone a prompt.
    assert set(corpus) == {"Button.tsx"}


def test_corpus_skips_oversized_files(tmp_path: Path) -> None:
    root = tmp_path / "app"
    _write(root / "small.ts", "const a = 1")
    _write(root / "bundle.js", "x" * (MAX_FILE_BYTES + 1))

    assert set(load_source_corpus(root)) == {"small.ts"}


def test_corpus_skips_undecodable_files(tmp_path: Path) -> None:
    root = tmp_path / "app"
    root.mkdir(parents=True)
    (root / "ok.ts").write_text("const a = 1")
    (root / "binary.ts").write_bytes(b"\xff\xfe\x00\x01 not utf-8")

    assert set(load_source_corpus(root)) == {"ok.ts"}


def test_search_finds_the_file_containing_the_anchor(tmp_path: Path) -> None:
    root = tmp_path / "app"
    _write(root / "Header.tsx", "export const Header = () => <nav />")
    _write(root / "Button.tsx", 'export const Button = () => <button id="hero-cta" />')

    matches = search_corpus(load_source_corpus(root), [_anchor(AnchorKind.ID, "hero-cta")])

    assert [match.path for match in matches] == ["Button.tsx"]
    assert matches[0].matched_anchors == ["hero-cta"]


def test_search_reports_real_line_numbers_and_a_snippet(tmp_path: Path) -> None:
    root = tmp_path / "app"
    _write(root / "Button.tsx", "\n".join(["// a", "// b", '<button id="hero-cta" />', "// d"]))

    match = search_corpus(load_source_corpus(root), [_anchor(AnchorKind.ID, "hero-cta")])[0]

    # The anchor is on line 3; the snippet must contain it, labelled with
    # that same number so a human can jump straight there.
    assert match.line_start <= 3 <= match.line_end
    assert '3: <button id="hero-cta" />' in match.snippet


def test_search_ranks_by_distinct_anchor_weight_not_repetition(tmp_path: Path) -> None:
    root = tmp_path / "app"
    # Repeats one low-weight class many times...
    _write(root / "Noisy.tsx", "\n".join(['<div class="btn-primary" />'] * 20))
    # ...versus one file matching an id (weight 5) plus the class (weight 2).
    _write(root / "Real.tsx", '<button id="hero-cta" class="btn-primary" />')

    matches = search_corpus(
        load_source_corpus(root),
        [_anchor(AnchorKind.ID, "hero-cta"), _anchor(AnchorKind.CLASS, "btn-primary")],
    )

    assert [match.path for match in matches] == ["Real.tsx", "Noisy.tsx"]
    assert matches[0].score > matches[1].score


def test_search_centres_the_snippet_on_the_densest_line(tmp_path: Path) -> None:
    root = tmp_path / "app"
    _write(
        root / "Page.tsx",
        "\n".join(
            ["// filler"] * 30
            + ['<div class="btn-primary" />']  # line 31: one anchor
            + ["// filler"] * 30
            + ['<button id="hero-cta" class="btn-primary" />']  # line 62: two anchors
        ),
    )

    match = search_corpus(
        load_source_corpus(root),
        [_anchor(AnchorKind.ID, "hero-cta"), _anchor(AnchorKind.CLASS, "btn-primary")],
    )[0]

    assert match.line_start <= 62 <= match.line_end
    assert 31 < match.line_start


def test_search_drops_anchors_that_match_too_many_files(tmp_path: Path) -> None:
    root = tmp_path / "app"
    # A class in every file discriminates nothing — that's the
    # document-frequency filter's whole job.
    for index in range(MAX_ANCHOR_FILE_MATCHES + 5):
        _write(root / f"c{index:03d}.tsx", '<div class="wrap-x" />')
    _write(root / "Real.tsx", '<div class="wrap-x" id="hero-cta" />')

    matches = search_corpus(
        load_source_corpus(root),
        [_anchor(AnchorKind.CLASS, "wrap-x"), _anchor(AnchorKind.ID, "hero-cta")],
    )

    assert [match.path for match in matches] == ["Real.tsx"]
    assert matches[0].matched_anchors == ["hero-cta"]


def test_search_returns_nothing_without_anchors(tmp_path: Path) -> None:
    root = tmp_path / "app"
    _write(root / "Button.tsx", '<button id="hero-cta" />')

    assert search_corpus(load_source_corpus(root), []) == []


def test_search_returns_nothing_when_evidence_is_absent(tmp_path: Path) -> None:
    root = tmp_path / "app"
    _write(root / "Button.tsx", "<button />")

    assert search_corpus(load_source_corpus(root), [_anchor(AnchorKind.ID, "nowhere")]) == []


def test_search_caps_the_number_of_candidates(tmp_path: Path) -> None:
    root = tmp_path / "app"
    for index in range(MAX_CANDIDATES + 6):
        _write(root / f"f{index:03d}.tsx", '<div id="hero-cta" />')

    matches = search_corpus(load_source_corpus(root), [_anchor(AnchorKind.ID, "hero-cta")])

    assert len(matches) == MAX_CANDIDATES


def test_snippet_truncates_very_long_lines(tmp_path: Path) -> None:
    root = tmp_path / "app"
    _write(root / "min.js", 'var a="hero-cta";' + "z" * 5_000)

    match = search_corpus(load_source_corpus(root), [_anchor(AnchorKind.TEXT, "hero-cta")])[0]

    # Minified/generated lines get cut rather than swallowing the prompt.
    assert len(max(match.snippet.splitlines(), key=len)) < MAX_LINE_CHARS + 20
