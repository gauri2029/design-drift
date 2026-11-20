"""The connection-string rewrite that lets a deployment boot.

Managed Postgres providers (Render, Heroku, Fly) hand out a URL with no
driver in the scheme. SQLAlchemy maps that to psycopg2, which
`create_async_engine` rejects — and because `alembic upgrade head` is the
container's start command, getting this wrong means the service never comes
up at all rather than failing on first request.

Cheap to test, expensive to debug from a deploy log, so it is tested.
"""

import pytest

from app.core.config import Settings


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        # What Render and Heroku actually emit.
        (
            "postgres://u:p@host:5432/db",
            "postgresql+asyncpg://u:p@host:5432/db",
        ),
        # The spelling some providers and tools use instead.
        (
            "postgresql://u:p@host:5432/db",
            "postgresql+asyncpg://u:p@host:5432/db",
        ),
        # Already explicit: must be left exactly as it is, or a local .env
        # and the test suite's own URL would be rewritten under them.
        (
            "postgresql+asyncpg://u:p@localhost:55432/design_drift",
            "postgresql+asyncpg://u:p@localhost:55432/design_drift",
        ),
    ],
)
def test_async_database_url_guarantees_an_async_driver(given: str, expected: str) -> None:
    assert Settings(database_url=given).async_database_url == expected


def test_the_rewrite_preserves_query_parameters() -> None:
    """Providers append parameters like sslmode, and dropping them would
    turn a working connection string into a failing one.
    """
    settings = Settings(database_url="postgres://u:p@host:5432/db?sslmode=require")
    assert settings.async_database_url == "postgresql+asyncpg://u:p@host:5432/db?sslmode=require"


def test_a_password_containing_the_scheme_is_not_mangled() -> None:
    """Only the leading scheme is rewritten, not every occurrence.

    A generated password can contain almost anything; a global replace
    would corrupt one that happened to contain the matched text.
    """
    settings = Settings(database_url="postgres://u:postgres://x@host:5432/db")
    assert settings.async_database_url == "postgresql+asyncpg://u:postgres://x@host:5432/db"
