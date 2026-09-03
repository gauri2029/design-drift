"""Unit tests for app.tools.apply_patch — the only code here that writes
to a user's checkout, so the cases that matter most are the ones where it
declines to."""

from pathlib import Path

import pytest

from app.agents.types import Patch
from app.tools.apply_patch import apply_patches, resolve_within
from app.tools.repo_search import SourceNotAccessibleError


def _patch(**overrides) -> Patch:
    defaults = {
        "file_path": "index.html",
        "line_start": 2,
        "line_end": 2,
        "original_code": '  <html lang="">',
        "replacement_code": '  <html lang="en">',
    }
    return Patch(**{**defaults, **overrides})


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text(
        '<!doctype html>\n  <html lang="">\n  <body>\n  </body>\n', encoding="utf-8"
    )
    return tmp_path


def test_an_approved_patch_is_spliced_into_the_file(checkout: Path) -> None:
    outcomes = apply_patches(checkout, [("html-has-lang", _patch())])

    assert outcomes["html-has-lang"].applied is True
    assert (checkout / "index.html").read_text() == (
        '<!doctype html>\n  <html lang="en">\n  <body>\n  </body>\n'
    )


def test_the_file_is_found_by_content_when_the_line_numbers_have_drifted(
    checkout: Path,
) -> None:
    """The reviewer approved a block of code, not a line number. If the
    file gained a line since the run, the patch should still land."""
    (checkout / "index.html").write_text(
        '<!-- added since the run -->\n<!doctype html>\n  <html lang="">\n  <body>\n',
        encoding="utf-8",
    )

    outcomes = apply_patches(checkout, [("html-has-lang", _patch())])

    assert outcomes["html-has-lang"].applied is True
    assert '<html lang="en">' in (checkout / "index.html").read_text()


def test_a_patch_whose_code_is_gone_is_skipped_and_the_file_untouched(
    checkout: Path,
) -> None:
    before = (checkout / "index.html").read_text()

    outcomes = apply_patches(
        checkout, [("html-has-lang", _patch(original_code="  <html lang=\"fr\">"))]
    )

    assert outcomes["html-has-lang"].applied is False
    assert "no longer in the file" in (outcomes["html-has-lang"].reason or "")
    assert (checkout / "index.html").read_text() == before


def test_an_ambiguous_block_is_skipped_rather_than_guessed(tmp_path: Path) -> None:
    """Two identical regions means we can't tell which one was approved.
    Picking either would be a coin flip on someone's source file."""
    (tmp_path / "page.html").write_text("<p>hi</p>\n<div/>\n<p>hi</p>\n", encoding="utf-8")

    outcomes = apply_patches(
        tmp_path,
        [
            (
                "duplicate",
                Patch(
                    file_path="page.html",
                    line_start=9,
                    line_end=9,
                    original_code="<p>hi</p>",
                    replacement_code="<p>bye</p>",
                ),
            )
        ],
    )

    assert outcomes["duplicate"].applied is False
    assert "bye" not in (tmp_path / "page.html").read_text()


def test_two_patches_to_one_file_both_land(tmp_path: Path) -> None:
    """Applied bottom-up, so splicing the first doesn't shift the second."""
    (tmp_path / "index.html").write_text("<a/>\n<b/>\n<c/>\n<d/>\n", encoding="utf-8")

    outcomes = apply_patches(
        tmp_path,
        [
            (
                "top",
                Patch(
                    file_path="index.html",
                    line_start=1,
                    line_end=1,
                    original_code="<a/>",
                    replacement_code="<a1/>\n<a2/>",
                ),
            ),
            (
                "bottom",
                Patch(
                    file_path="index.html",
                    line_start=4,
                    line_end=4,
                    original_code="<d/>",
                    replacement_code="<d1/>",
                ),
            ),
        ],
    )

    assert outcomes["top"].applied and outcomes["bottom"].applied
    assert (tmp_path / "index.html").read_text() == "<a1/>\n<a2/>\n<b/>\n<c/>\n<d1/>\n"


def test_a_patch_pointing_outside_the_checkout_is_refused(tmp_path: Path) -> None:
    """A file_path comes from an LLM, so traversal is a shape the input can
    take — and this one writes."""
    root = tmp_path / "checkout"
    root.mkdir()
    (tmp_path / "outside.html").write_text("<p>secret</p>\n", encoding="utf-8")

    outcomes = apply_patches(
        root,
        [
            (
                "escape",
                Patch(
                    file_path="../outside.html",
                    line_start=1,
                    line_end=1,
                    original_code="<p>secret</p>",
                    replacement_code="<p>owned</p>",
                ),
            )
        ],
    )

    assert outcomes["escape"].applied is False
    assert "outside" in (outcomes["escape"].reason or "")
    assert (tmp_path / "outside.html").read_text() == "<p>secret</p>\n"


def test_a_patch_targeting_a_non_source_file_is_refused(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")

    with pytest.raises(SourceNotAccessibleError):
        resolve_within(tmp_path, ".env")


def test_a_missing_file_is_reported_not_created(tmp_path: Path) -> None:
    outcomes = apply_patches(tmp_path, [("gone", _patch())])

    assert outcomes["gone"].applied is False
    assert not (tmp_path / "index.html").exists()


def test_a_file_without_a_trailing_newline_keeps_not_having_one(tmp_path: Path) -> None:
    """Flipping this turns one approved change into a whole-file diff."""
    (tmp_path / "index.html").write_text('<!doctype html>\n  <html lang="">', encoding="utf-8")

    apply_patches(tmp_path, [("html-has-lang", _patch())])

    assert (tmp_path / "index.html").read_text() == '<!doctype html>\n  <html lang="en">'
