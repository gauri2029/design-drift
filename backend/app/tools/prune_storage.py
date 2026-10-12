"""Delete stored artifacts that no database row references any more.

Deleting a project removes its files (see services.projects.delete_project),
so this is not that. Orphans come from the gaps around it: runs that failed
after writing a screenshot but before committing a row, and projects deleted
before the delete feature existed. Nothing will ever reach those files again,
and a full-page capture is several megabytes.

Run it by hand, not on a schedule:

    uv run python -m app.tools.prune_storage           # report only
    uv run python -m app.tools.prune_storage --delete  # actually remove

Dry by default because it is the kind of command that should not surprise
anyone the first time they run it.
"""

import argparse
import asyncio
import shutil
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.design_analysis import DesignAnalysis
from app.models.project import Project
from app.models.scan import Scan

# Each storage group is keyed by the id of the row that owns it, so
# "referenced" is just "this directory name is still an id somewhere".
_GROUPS = ("figma", "design-analyses", "scans")


async def _referenced_ids() -> set[str]:
    async with async_session_factory() as session:
        ids: set[str] = set()
        for model in (Project, DesignAnalysis, Scan):
            for row in (await session.execute(select(model.id))).scalars().all():
                ids.add(str(row))
        return ids


def _is_uuid(name: str) -> bool:
    try:
        UUID(name)
    except ValueError:
        return False
    return True


def prune(referenced: set[str], *, delete: bool) -> int:
    """The filesystem half, given the ids that are still in use.

    Split from `main` so the caller owns the event loop: this is pure
    synchronous filesystem work, and a test (or any other caller) already
    inside a loop cannot call asyncio.run().
    """
    root = Path(get_settings().storage_root).resolve()
    if not root.is_dir():
        print(f"storage root {root} does not exist", file=sys.stderr)
        return 1

    orphans: list[tuple[Path, int]] = []

    for group in _GROUPS:
        directory = root / group
        if not directory.is_dir():
            continue
        for child in sorted(directory.iterdir()):
            # Only id-named directories are ours to judge; anything else
            # was put there by a human and is left alone.
            if not child.is_dir() or not _is_uuid(child.name):
                continue
            if child.name in referenced:
                continue
            size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
            orphans.append((child, size))

    if not orphans:
        print("no orphaned artifacts")
        return 0

    total = sum(size for _, size in orphans)
    for path, size in orphans:
        print(f"  {path.relative_to(root)}  {size / 1e6:.1f}MB")
    print(f"\n{len(orphans)} orphaned directories, {total / 1e6:.1f}MB")

    if not delete:
        print("\nnothing deleted. Re-run with --delete to remove them.")
        return 0

    for path, _ in orphans:
        # Re-checked immediately before the rmtree: this function builds
        # the paths itself, but a deletion loop is the wrong place to
        # assume that stays true.
        if root not in path.resolve().parents:
            print(f"refusing to delete outside the storage root: {path}", file=sys.stderr)
            return 1
        shutil.rmtree(path)
    print(f"\ndeleted {len(orphans)} directories, freed {total / 1e6:.1f}MB")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delete",
        action="store_true",
        help="actually remove the orphans (without this, only reports them)",
    )
    args = parser.parse_args()
    return prune(asyncio.run(_referenced_ids()), delete=args.delete)


if __name__ == "__main__":
    raise SystemExit(main())
