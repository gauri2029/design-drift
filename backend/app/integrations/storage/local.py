from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings


class LocalStorageBackend:
    """Filesystem-backed `StorageBackend`, rooted at a configured directory."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _resolve(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if self._root.resolve() not in path.parents and path != self._root.resolve():
            raise ValueError(f"storage key escapes root: {key!r}")
        return path

    def save(self, key: str, data: bytes) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def read(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()


@lru_cache
def get_storage_backend() -> LocalStorageBackend:
    settings = get_settings()
    return LocalStorageBackend(root=Path(settings.storage_root))
