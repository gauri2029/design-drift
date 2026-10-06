"""Account creation and sign-in.

Plain async service functions, matching app.services.projects — no agent or
graph involved, because there's no decision here worth a state machine.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest


class EmailAlreadyRegisteredError(Exception):
    """Signup for an address that already has an account."""


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    # Compared lowercased on both sides so an account can't be shadowed by
    # the same address in different case.
    result = await db.execute(select(User).where(func.lower(User.email) == email.strip().lower()))
    return result.scalar_one_or_none()


async def get_user(db: AsyncSession, user_id: UUID) -> User | None:
    return await db.get(User, user_id)


async def create_user(db: AsyncSession, payload: SignupRequest) -> User:
    """Register an account, or raise if the address is taken.

    The uniqueness check races with a concurrent signup for the same
    address; the unique index on users.email is what actually prevents a
    duplicate. This check exists to turn the common case into a 409 instead
    of a 500, not to be the guarantee.
    """
    email = payload.email.strip().lower()
    if await get_user_by_email(db, email) is not None:
        raise EmailAlreadyRegisteredError(email)

    user = User(
        email=email,
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, payload: LoginRequest) -> User | None:
    """The user those credentials belong to, or None.

    One return value for "no such account" and "wrong password", because
    the caller must not tell them apart — distinguishing them turns the
    login endpoint into a way to enumerate who has an account.
    """
    user = await get_user_by_email(db, payload.email)
    if user is None:
        return None
    if not verify_password(payload.password, user.password_hash):
        return None
    return user
