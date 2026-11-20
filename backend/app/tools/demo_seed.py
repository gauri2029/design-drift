"""Load an exported demo fixture into this database. Run once per deployment.

Pairs with `app.tools.demo_export`: that reads a real run out of a developer
machine's database, this writes it into the deployment's, under a dedicated
showcase account that every anonymous visitor is resolved to (see
app.services.demo and app.api.v1.auth.current_user_or_demo).

Idempotent. Re-running replaces the showcase account's projects rather than
adding a second copy, so a redeploy that re-seeds does not accumulate
duplicates.

Usage (on the deployed instance, after migrations):
    uv run python -m app.tools.demo_seed --fixture ../demo/recipes-gallery

The showcase password is read from DEMO_USER_PASSWORD if set, and otherwise
generated and discarded: nobody needs to log in as the demo account, because
anonymous visitors are resolved to it automatically. A random unknown
password is the safer default — it means there is no shared credential to
leak, and the account cannot be signed into at all.
"""

import argparse
import asyncio
import json
import os
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import async_session_factory
from app.integrations.storage.local import get_storage_backend
from app.models.design_analysis import DesignAnalysis
from app.models.project import Project
from app.models.user import User
from app.services import projects as projects_service

_SUPPORTED_FIXTURE_VERSION = 1


async def seed(fixture_dir: Path) -> int:
    settings = get_settings()
    if not settings.demo_mode:
        print(
            "DEMO_MODE is not enabled, so a seeded showcase account would be\n"
            "unreachable. Set DEMO_MODE=true and re-run.",
            file=sys.stderr,
        )
        return 2

    fixture_path = fixture_dir / "fixture.json"
    if not fixture_path.exists():
        print(f"no fixture at {fixture_path}", file=sys.stderr)
        return 2

    fixture: dict[str, Any] = json.loads(fixture_path.read_text())
    version = fixture.get("fixture_version")
    if version != _SUPPORTED_FIXTURE_VERSION:
        print(
            f"fixture version {version!r} is not supported "
            f"(this tool reads {_SUPPORTED_FIXTURE_VERSION}); re-export it",
            file=sys.stderr,
        )
        return 2

    storage = get_storage_backend()

    async with async_session_factory() as db:
        email = settings.demo_user_email.strip().lower()
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

        if user is None:
            password = os.environ.get("DEMO_USER_PASSWORD") or secrets.token_urlsafe(32)
            user = User(
                email=email,
                name=fixture.get("demo_user_name", "Design Drift Demo"),
                password_hash=hash_password(password),
            )
            db.add(user)
            await db.flush()
            print(f"created showcase account {email}")
        else:
            print(f"reusing showcase account {email}")

        # Replace rather than append, so re-seeding is idempotent. Goes
        # through the service so artifacts and workspaces are cleaned up
        # the same way a user-initiated delete would clean them.
        existing = await projects_service.list_projects(db, owner_id=user.id)
        for project in existing:
            print(f"  removing previous demo project {project.name}")
            await projects_service.delete_project(db, project, storage)

        project_data = fixture["project"]
        project = Project(
            owner_id=user.id,
            name=project_data["name"],
            figma_file_key=project_data["figma_file_key"],
            figma_node_id=project_data["figma_node_id"],
            target_url=project_data["target_url"],
            target_selector=project_data.get("target_selector"),
            github_repo_full_name=project_data.get("github_repo_full_name"),
            github_branch=project_data.get("github_branch"),
            # Never set from a fixture: it names a directory on whatever
            # machine the export came from. Leaving it null is what stops
            # the deployment trying to read a checkout it does not have.
            source_path=None,
            figma_data=project_data.get("figma_data"),
            figma_fetched_at=datetime.now(UTC),
        )
        db.add(project)
        await db.flush()

        images: dict[str, str] = fixture.get("images", {})

        # Images are re-keyed under the new project/run ids, so they land
        # where the API's own read paths look for them.
        if "figma_screenshot_key" in images:
            key = f"figma/{project.id}/preview.png"
            storage.save(key, (fixture_dir / images["figma_screenshot_key"]).read_bytes())
            project.figma_screenshot_key = key

        analysis_data = fixture["analysis"]
        analysis = DesignAnalysis(
            project_id=project.id,
            model=analysis_data["model"],
            result=analysis_data["result"],
            target_url=analysis_data.get("target_url"),
            source_commit_sha=analysis_data.get("source_commit_sha"),
            verification_target_url=analysis_data.get("verification_target_url"),
            comparison_result=analysis_data.get("comparison_result"),
            visual_comparison=analysis_data.get("visual_comparison"),
            accessibility_report=analysis_data.get("accessibility_report"),
            accessibility_interpretation=analysis_data.get("accessibility_interpretation"),
            aggregated_findings=analysis_data.get("aggregated_findings"),
            code_analysis=analysis_data.get("code_analysis"),
            fix_proposal=analysis_data.get("fix_proposal"),
            fix_review=analysis_data.get("fix_review"),
            fix_application=analysis_data.get("fix_application"),
            verification=analysis_data.get("verification"),
        )
        db.add(analysis)
        await db.flush()

        for column, filename in images.items():
            if column == "figma_screenshot_key":
                continue
            source = fixture_dir / filename
            if not source.exists():
                print(f"  warning: fixture names {filename}, which is missing", file=sys.stderr)
                continue
            key = f"design-analyses/{analysis.id}/{filename}"
            storage.save(key, source.read_bytes())
            setattr(analysis, column, key)

        await db.commit()
        print(f"seeded project {project.name} with run {analysis.id}")

    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    args = parser.parse_args()
    return await seed(args.fixture)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
