"""Signup, login, "who am I", and the two identity dependencies.

Every project-scoped route is owner-filtered, so it needs an identity:

`require_current_user`
    A valid bearer token or 401. What every write depends on.

`current_user_or_demo`
    The same, except an anonymous caller resolves to the read-only showcase
    account when demo mode is on (see app.services.demo). What the read
    routes depend on, so the public deployment can be browsed without a
    signup while still going through the ordinary ownership filter.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserRead
from app.services import auth as auth_service
from app.services import demo as demo_service
from app.services import rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])

# auto_error=False so a missing header reaches our own handler and returns
# the same 401 shape as a bad one, rather than FastAPI's 403.
_bearer = HTTPBearer(auto_error=False)

_INVALID_CREDENTIALS = "incorrect email or password"


async def require_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """The signed-in user, or 401. Depend on this to protect a route."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized

    # A token can outlive the account it names, so the row is checked rather
    # than trusted from the signature alone.
    user = await auth_service.get_user(db, user_id)
    if user is None:
        raise unauthorized
    return user


async def current_user_or_demo(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """The signed-in user, or the showcase account for an anonymous caller.

    This is what lets a recruiter open the deployed app and browse a real
    run without signing up. An anonymous request is resolved to the demo
    account, so it sees exactly that account's projects through the normal
    owner-filtered queries — no separate unauthenticated read path, and
    therefore no second place where an ownership filter could be forgotten.

    Depend on this only for *reads*. Writes keep `require_current_user` and
    additionally pass through `app.services.demo.guard_mutation`, so an
    anonymous caller resolved to the demo account cannot spend money or
    change what the demo shows.

    With demo mode off, or before the account is seeded, this behaves
    identically to `require_current_user`: no token still means 401.
    """
    if credentials is not None:
        return await require_current_user(credentials, db)

    demo_user = await demo_service.get_demo_user(db)
    if demo_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return demo_user


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    settings = get_settings()

    # The one unauthenticated write on a public deployment. Throttled per IP
    # so a script can't mint accounts in bulk; see app.services.rate_limit
    # for what this does and does not protect against.
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limit.check(f"signup:{client_ip}", settings.signup_rate_limit_per_hour):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many signup attempts from this address; try again later",
        )

    # Claiming the showcase address would hand someone write access to the
    # demo data every visitor reads. The address is public (it's in the
    # deployment config), so this has to be refused explicitly rather than
    # relying on the seeded row already existing.
    if payload.email.strip().lower() == settings.demo_user_email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an account with that email already exists",
        )

    try:
        user = await auth_service.create_user(db, payload)
    except auth_service.EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an account with that email already exists",
        ) from exc
    return TokenResponse(
        access_token=create_access_token(user.id), user=UserRead.model_validate(user)
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await auth_service.authenticate(db, payload)
    if user is None:
        # Same message whether the address is unknown or the password is
        # wrong — see auth_service.authenticate.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS)
    return TokenResponse(
        access_token=create_access_token(user.id), user=UserRead.model_validate(user)
    )


@router.get("/me", response_model=UserRead)
async def read_current_user(user: User = Depends(require_current_user)) -> UserRead:
    """Lets the frontend check a stored token is still good on load."""
    return UserRead.model_validate(user)
