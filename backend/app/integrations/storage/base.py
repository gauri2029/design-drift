from typing import Protocol


class StorageBackend(Protocol):
    """Content-addressable-ish artifact storage.

    Callers deal only in string keys (e.g. "figma/<project_id>/preview.png")
    and bytes. Swapping the local-disk implementation for an S3-backed one
    later (Phase 9) means adding a new class here, not touching callers.
    """

    def save(self, key: str, data: bytes) -> str:
        """Persist `data` under `key`, returning a locator (path or URL)."""
        ...

    def read(self, key: str) -> bytes:
        """Return the bytes previously saved under `key`."""
        ...

    def delete(self, key: str) -> None:
        """Remove `key` if it exists.

        Deliberately not an error when the key is absent: callers delete a
        project's artifacts from the keys recorded on its rows, and a run
        that failed midway can leave a key recorded whose file was never
        written. Deleting the rest matters more than reporting that one.
        """
        ...
