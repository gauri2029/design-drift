"""What the frontend needs to know to label the demo honestly.

One unauthenticated GET. The frontend asks it on load and, when demo mode
is on, says plainly that the results on screen are stored output from real
agent runs and that executing the agents is disabled here. Without this the
UI would have to infer the demo from a 403 after the visitor had already
clicked something, which is a worse way to find out.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.services import demo as demo_service

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoStatus(BaseModel):
    """Whether this deployment is serving the public showcase.

    `enabled` is the config flag; `seeded` is whether the showcase account
    actually exists yet. Both, because a deployment switched on before its
    seed has run should present as a normal empty app rather than promising
    a demo that isn't there.
    """

    enabled: bool
    seeded: bool
    # The signed-out visitor's identity, so the UI can show whose projects
    # these are instead of an empty account menu.
    user_name: str | None = None


@router.get("/status", response_model=DemoStatus)
async def demo_status(db: AsyncSession = Depends(get_db)) -> DemoStatus:
    settings = get_settings()
    if not settings.demo_mode:
        return DemoStatus(enabled=False, seeded=False)

    user = await demo_service.get_demo_user(db)
    return DemoStatus(
        enabled=True,
        seeded=user is not None,
        user_name=user.name if user else None,
    )
