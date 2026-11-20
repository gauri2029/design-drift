"""Export one real analysis run to a portable fixture, for the public demo.

Why export rather than hand-write a fixture
-------------------------------------------
The demo has to show what the agents really produced, or it is a mock-up
with extra steps (docs/principles.md #2). So the fixture is *extracted from
a run that actually happened* on the developer's machine: the findings, the
located files and line numbers, the proposed patches, the verification
verdict, and the PNGs the capture and diff produced. Nothing here is
authored by hand, and nothing is embellished — this tool copies rows.

What it deliberately does not export
------------------------------------
Source code. A located finding names a file path, a line range, and the few
lines of `code_evidence` the agent quoted to justify the match — that is
part of the finding and is what makes the demo worth looking at. But the
checkout itself, the full file contents, and the cloned workspace never
enter the fixture, and `--check-only` prints every path and quoted snippet
so the developer can read exactly what would ship before it does.

Usage
    # see what would be exported, and from which run
    uv run python -m app.tools.demo_export --project-id <uuid> --check-only

    # write it
    uv run python -m app.tools.demo_export --project-id <uuid> \
        --out ../demo/recipes-gallery

Then `app.tools.demo_seed` loads that directory into the deployed database.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.db.session import async_session_factory
from app.integrations.storage.local import get_storage_backend
from app.models.design_analysis import DesignAnalysis
from app.models.project import Project

# The run columns that carry the agents' output. Listed explicitly rather
# than reflected off the model so adding a column is a deliberate decision
# about whether it belongs in a public fixture, not an automatic one.
_RUN_JSON_COLUMNS = (
    "result",
    "comparison_result",
    "visual_comparison",
    "accessibility_report",
    "accessibility_interpretation",
    "aggregated_findings",
    "code_analysis",
    "fix_proposal",
    "fix_review",
    "fix_application",
    "verification",
)

# Storage keys on a run, mapped to the filename they get in the fixture.
_RUN_IMAGE_COLUMNS = {
    "production_screenshot_key": "production.png",
    "diff_image_key": "diff.png",
    "verification_screenshot_key": "verification.png",
    "verification_diff_image_key": "verification-diff.png",
}


def _dict_list(container: dict[str, object] | None, key: str) -> list[dict[str, object]]:
    """The list of dicts at `container[key]`, or empty.

    JSONB columns are typed `dict[str, object]`, so anything nested is
    `object` until checked. Narrowing here once keeps the callers readable
    and means a fixture with an unexpected shape yields nothing rather
    than raising halfway through an export.
    """
    if not container:
        return []
    value = container.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _quoted_code(analysis: DesignAnalysis) -> list[str]:
    """Every snippet of the target repo's source this fixture would carry.

    Printed by --check-only. The point is that the developer sees the
    actual third-party code before deciding to publish it, rather than
    trusting a promise that it is only a few lines.
    """
    snippets: list[str] = []
    for location in _dict_list(analysis.code_analysis, "locations"):
        inner = location.get("location")
        if isinstance(inner, dict) and inner.get("code_evidence"):
            snippets.append(
                f"{inner.get('file_path')}:{inner.get('line_start')}-{inner.get('line_end')}\n"
                f"{inner.get('code_evidence')}"
            )

    for fix in _dict_list(analysis.fix_proposal, "fixes"):
        patch = fix.get("patch")
        if isinstance(patch, dict):
            snippets.append(
                f"{patch.get('file_path')}:{patch.get('line_start')}-{patch.get('line_end')}\n"
                f"--- original ---\n{patch.get('original_code')}\n"
                f"--- replacement ---\n{patch.get('replacement_code')}"
            )
    return snippets


async def _load(project_id: UUID, analysis_id: UUID | None) -> tuple[Project, DesignAnalysis]:
    async with async_session_factory() as db:
        project = await db.get(Project, project_id)
        if project is None:
            raise SystemExit(f"no project {project_id}")

        query = select(DesignAnalysis).where(DesignAnalysis.project_id == project_id)
        if analysis_id is not None:
            query = query.where(DesignAnalysis.id == analysis_id)
        rows = list((await db.execute(query.order_by(DesignAnalysis.created_at.desc()))).scalars())
        if not rows:
            raise SystemExit(f"project {project_id} has no analysis runs")

        # The most *complete* run, not simply the newest. A demo is worth
        # more the further through the workflow it got: a run that was
        # reviewed and applied shows the human-approval step, which is the
        # part of the product worth seeing, while the newest run may have
        # stopped at "patches proposed".
        #
        # Ties break toward the newer run, because rows are newest-first
        # and max() keeps the first of an equal pair.
        chosen = max(rows, key=_completeness)
        return project, chosen


def _completeness(analysis: DesignAnalysis) -> int:
    """How far through the workflow this run got, as a count of stages.

    Ordered, not weighted: each stage implies the ones before it, so
    counting them ranks runs the same way reading them would.
    """
    stages = (
        analysis.aggregated_findings,
        analysis.code_analysis,
        analysis.fix_proposal,
        analysis.fix_review,
        analysis.fix_application,
        analysis.verification,
    )
    return sum(1 for stage in stages if stage)


def _describe(project: Project, analysis: DesignAnalysis) -> None:
    print(f"project:  {project.name}  ({project.id})")
    print(f"  target: {project.target_url}")
    print(f"  figma:  {project.figma_file_key} / {project.figma_node_id}")
    print(f"  repo:   {project.github_repo_full_name or project.source_path or '(none)'}")
    print(f"run:      {analysis.id}  created {analysis.created_at}")
    print(f"  model:  {analysis.model}")

    findings = _dict_list(analysis.aggregated_findings, "findings")
    print(f"  findings: {len(findings)}")
    for finding in findings:
        print(f"    [{finding.get('priority')}] {finding.get('title')}")

    for column in _RUN_JSON_COLUMNS:
        print(f"  {column}: {'present' if getattr(analysis, column) else 'null'}")
    for column in _RUN_IMAGE_COLUMNS:
        print(f"  {column}: {getattr(analysis, column) or 'null'}")

    snippets = _quoted_code(analysis)
    print(f"\n--- third-party source quoted in this fixture ({len(snippets)} snippet(s)) ---")
    for snippet in snippets:
        print(snippet)
        print("-" * 60)
    if snippets:
        print(
            "Read the above before exporting. These lines come from the target\n"
            "repository and would be published with the demo."
        )


def _write_fixture(out: Path, project: Project, analysis: DesignAnalysis) -> None:
    """Write the fixture directory. Sync: it is all local filesystem IO."""
    out.mkdir(parents=True, exist_ok=True)
    storage = get_storage_backend()

    images: dict[str, str] = {}
    for column, filename in _RUN_IMAGE_COLUMNS.items():
        key = getattr(analysis, column)
        if not key:
            continue
        try:
            (out / filename).write_bytes(storage.read(key))
        except OSError as exc:
            print(f"  warning: could not read {key}: {exc}", file=sys.stderr)
            continue
        images[column] = filename

    if project.figma_screenshot_key:
        try:
            (out / "figma.png").write_bytes(storage.read(project.figma_screenshot_key))
            images["figma_screenshot_key"] = "figma.png"
        except OSError as exc:
            print(f"  warning: could not read figma preview: {exc}", file=sys.stderr)

    fixture: dict[str, Any] = {
        # A schema marker, so demo_seed can refuse a fixture it predates
        # rather than half-loading one.
        "fixture_version": 1,
        "project": {
            "name": project.name,
            "figma_file_key": project.figma_file_key,
            "figma_node_id": project.figma_node_id,
            "target_url": project.target_url,
            "target_selector": project.target_selector,
            "github_repo_full_name": project.github_repo_full_name,
            "github_branch": project.github_branch,
            # Not exported: source_path. It names a directory on the
            # developer's machine and means nothing in the deployment.
            "figma_data": project.figma_data,
        },
        "analysis": {
            "model": analysis.model,
            "target_url": analysis.target_url,
            "source_commit_sha": analysis.source_commit_sha,
            "verification_target_url": analysis.verification_target_url,
            **{column: getattr(analysis, column) for column in _RUN_JSON_COLUMNS},
        },
        "images": images,
    }

    (out / "fixture.json").write_text(json.dumps(fixture, indent=2, default=str))
    print(f"\nwrote {out / 'fixture.json'} and {len(images)} image(s) to {out}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True, type=UUID)
    parser.add_argument(
        "--analysis-id",
        type=UUID,
        default=None,
        help="a specific run; default is the newest verified one",
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="print what would be exported, including every quoted source snippet",
    )
    args = parser.parse_args()

    project, analysis = await _load(args.project_id, args.analysis_id)
    _describe(project, analysis)

    if args.check_only:
        return 0
    if args.out is None:
        print("\nrefusing to write without --out (or pass --check-only)", file=sys.stderr)
        return 2

    _write_fixture(args.out, project, analysis)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
