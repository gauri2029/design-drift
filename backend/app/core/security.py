"""Password hashing and access-token minting.

Two primitives, kept apart from the auth service so the service reads as
"find the user, check the password, issue a token" rather than as crypto.

argon2 rather than bcrypt: it's OWASP's current recommendation, has no
72-byte input truncation, and argon2-cffi needs no configuration to be
safe by default. PyJWT rather than a session table because the frontend is
a separate origin talking to a stateless API — there is nothing to look up
a session cookie against.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()

_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """False for a wrong password, rather than raising.

    argon2 signals every outcome by exception, and the three cases are not
    in one hierarchy: VerifyMismatchError (wrong password) and
    VerificationError both derive from Argon2Error, but InvalidHashError —
    raised when the stored string isn't an argon2 hash at all — derives from
    ValueError. All three mean the same thing to a caller, "don't sign this
    person in", so all three are caught; missing the third would turn a
    corrupt password_hash column into a 500 on the login endpoint.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: UUID) -> str:
    """A signed token naming the user, expiring per settings.

    `sub` is a string because RFC 7519 requires it; a UUID would serialize
    but fail validation on the way back in.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> UUID | None:
    """The user id a token names, or None if it isn't one we'd honour.

    Expiry, a bad signature and a malformed token all collapse to None:
    every one of them means "not authenticated", and the caller returns the
    same 401 regardless. Saying which would tell an attacker whether they
    had the shape right.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[_ALGORITHM])
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None
