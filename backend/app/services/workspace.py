"""Where a GitHub repository is checked out for one analysis run.

One directory per analysis, never reused:

    {workspace_root}/{project_id}/{analysis_id}/

Per-run rather than per-project because a run's findings cite file paths
and line numbers at one commit. If a later run re-cloned over the same
directory, every earlier run's line numbers would silently start pointing
at different code — and the patches an earlier run proposed would be
applied against a tree they were never computed from.

Nothing is deleted here. Reviewing and applying a fix happens minutes or
hours after the run, in separate requests, so a workspace has to outlive
the run that made it.
"""

import shutil
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.tools.repo_search import SourceNotAccessibleError


def workspace_root() -> Path:
    return Path(get_settings().workspace_root).resolve()


def workspace_for(project_id: UUID, analysis_id: UUID) -> Path:
    """The directory for one run's checkout, containment-checked.

    Both ids are UUIDs rather than anything user-supplied, so traversal
    isn't reachable today — the check is here because that is a property of
    the *callers*, and this function is the one place a future caller would
    pass something looser.
    """
    root = workspace_root()
    candidate = (root / str(project_id) / str(analysis_id)).resolve()
    if root not in candidate.parents:
        raise SourceNotAccessibleError("workspace path resolves outside the workspace root")
    return candidate


def reset(path: Path) -> None:
    """Clear a workspace directory so a clone can write into it.

    git refuses to clone into a non-empty directory, and a half-written
    checkout from an interrupted run would otherwise be analyzed as if it
    were complete.
    """
    if not path.exists():
        return
    if workspace_root() not in path.resolve().parents:
        raise SourceNotAccessibleError("refusing to delete a path outside the workspace root")
    shutil.rmtree(path)
