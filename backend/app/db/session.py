from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# echo=False by default; flip via app_env if we want SQL logging locally later.
# async_database_url, not database_url: a managed provider's connection
# string names no driver, and create_async_engine rejects the sync one
# SQLAlchemy would pick by default (see Settings.async_database_url).
engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    # Managed Postgres closes idle connections, and a pooled connection
    # that died since its last use surfaces as a failed request on the
    # next one. pre_ping costs a round trip and removes that class of
    # error entirely.
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped async DB session."""
    async with async_session_factory() as session:
        yield session
