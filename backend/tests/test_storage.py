import pytest

from app.integrations.storage.local import LocalStorageBackend


def test_save_then_read_roundtrips(tmp_path) -> None:
    backend = LocalStorageBackend(root=tmp_path)

    path = backend.save("figma/proj-1/preview.png", b"fake-png-bytes")

    assert path == str(tmp_path / "figma/proj-1/preview.png")
    assert backend.read("figma/proj-1/preview.png") == b"fake-png-bytes"


def test_save_creates_missing_parent_directories(tmp_path) -> None:
    backend = LocalStorageBackend(root=tmp_path)

    backend.save("a/b/c/file.bin", b"data")

    assert (tmp_path / "a/b/c/file.bin").read_bytes() == b"data"


def test_key_cannot_escape_root(tmp_path) -> None:
    backend = LocalStorageBackend(root=tmp_path)

    with pytest.raises(ValueError, match="escapes root"):
        backend.save("../outside.txt", b"nope")
