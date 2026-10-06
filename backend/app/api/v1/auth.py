"""Signup, login, and "who am I".

No existing route requires authentication: projects, scans and reviews stay
reachable exactly as before. Signing in gates the frontend and establishes
the identity that per-user ownership will later attach to, which is why
`require_current_user` lives here ready to be depended on rather than being
wired into routes that have no owner column to filter by yet.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserRead
from app.services import auth as auth_service

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


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
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
