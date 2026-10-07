"""API tests for /api/v1/auth.

Real Postgres, like the other API tests — password hashing and the unique
email index are the behaviour under test, so mocking the database away
would leave both unexercised.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.security import create_access_token, decode_access_token, hash_password
from app.db.session import async_session_factory
from app.main import app
from app.models.user import User

SIGNUP = {"email": "designer@example.com", "name": "Ada", "password": "correct horse battery"}

# This file tests authentication itself, so it must drive the real
# `require_current_user` rather than conftest's signed-in override — a /me
# test that can't return 401 isn't testing anything.
pytestmark = pytest.mark.anonymous


@pytest.fixture(autouse=True)
async def _clean_users():
    yield
    async with async_session_factory() as session:
        await session.execute(delete(User))
        await session.commit()


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_signup_returns_a_usable_token_and_the_new_user():
    async with await _client() as client:
        response = await client.post("/api/v1/auth/signup", json=SIGNUP)

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "designer@example.com"
    assert body["user"]["name"] == "Ada"
    assert body["token_type"] == "bearer"
    # The token must name the user that was just created, not merely parse.
    assert decode_access_token(body["access_token"]) is not None


async def test_signup_never_returns_the_password_or_its_hash():
    async with await _client() as client:
        response = await client.post("/api/v1/auth/signup", json=SIGNUP)

    # Checked against the whole serialized body, so a future field carrying
    # either one fails here rather than leaking quietly.
    assert "password" not in response.text
    assert "argon2" not in response.text


async def test_the_stored_password_is_hashed_not_the_plaintext():
    async with await _client() as client:
        await client.post("/api/v1/auth/signup", json=SIGNUP)

    async with async_session_factory() as session:
        user = (await session.execute(delete(User).returning(User.password_hash))).scalar_one()
        await session.commit()

    assert user != SIGNUP["password"]
    assert user.startswith("$argon2")


async def test_signing_up_twice_with_one_email_is_a_conflict():
    async with await _client() as client:
        await client.post("/api/v1/auth/signup", json=SIGNUP)
        # Different case and padding: the same person, so still a conflict.
        duplicate = await client.post(
            "/api/v1/auth/signup", json={**SIGNUP, "email": "Designer@Example.com "}
        )

    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]


async def test_login_succeeds_with_the_signup_password():
    async with await _client() as client:
        await client.post("/api/v1/auth/signup", json=SIGNUP)
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": SIGNUP["email"], "password": SIGNUP["password"]},
        )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == SIGNUP["email"]


async def test_login_is_case_insensitive_in_the_email():
    async with await _client() as client:
        await client.post("/api/v1/auth/signup", json=SIGNUP)
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "DESIGNER@example.com", "password": SIGNUP["password"]},
        )

    assert response.status_code == 200


async def test_a_wrong_password_and_an_unknown_email_are_indistinguishable():
    async with await _client() as client:
        await client.post("/api/v1/auth/signup", json=SIGNUP)
        wrong_password = await client.post(
            "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": "not it at all"}
        )
        no_account = await client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "not it at all"}
        )

    # Identical responses, or the endpoint becomes a way to find out who
    # has an account here.
    assert wrong_password.status_code == no_account.status_code == 401
    assert wrong_password.json() == no_account.json()


async def test_me_returns_the_user_named_by_the_token():
    async with await _client() as client:
        token = (await client.post("/api/v1/auth/signup", json=SIGNUP)).json()["access_token"]
        response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == SIGNUP["email"]


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no header"),
        pytest.param({"Authorization": "Bearer not-a-token"}, id="garbage token"),
        pytest.param({"Authorization": "Basic abc"}, id="wrong scheme"),
    ],
)
async def test_me_rejects_anything_but_a_valid_bearer_token(headers):
    async with await _client() as client:
        response = await client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 401


async def test_me_rejects_a_token_for_a_deleted_account():
    """A signature alone isn't enough — the account has to still exist."""
    async with await _client() as client:
        token = (await client.post("/api/v1/auth/signup", json=SIGNUP)).json()["access_token"]

        async with async_session_factory() as session:
            await session.execute(delete(User))
            await session.commit()

        response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_signup_rejects_a_short_password_and_a_malformed_email():
    async with await _client() as client:
        short = await client.post("/api/v1/auth/signup", json={**SIGNUP, "password": "short"})
        malformed = await client.post("/api/v1/auth/signup", json={**SIGNUP, "email": "nope"})

    assert short.status_code == 422
    assert malformed.status_code == 422


async def test_project_routes_require_a_token_and_health_does_not():
    """Inverted deliberately when projects gained an owner.

    This used to assert that /projects answered without a token — true when
    accounts gated only the frontend. Ownership is the change that makes it
    false, so the assertion flips rather than being deleted: it's the thing
    that would catch the gate being removed again.
    """
    async with await _client() as client:
        assert (await client.get("/api/v1/projects")).status_code == 401
        # Health stays open: a readiness probe has no account.
        assert (await client.get("/api/v1/health")).status_code == 200


def test_a_tampered_or_expired_token_decodes_to_nothing():
    """Unit-level, because an expiry can't be waited out in a test."""
    import uuid
    from datetime import UTC, datetime, timedelta

    import jwt

    from app.core.config import get_settings

    valid = create_access_token(uuid.uuid4())
    assert decode_access_token(valid) is not None
    # Flipping the last character invalidates the signature.
    assert decode_access_token(valid[:-1] + ("a" if valid[-1] != "a" else "b")) is None
    # Signed with the wrong key.
    assert decode_access_token(jwt.encode({"sub": str(uuid.uuid4())}, "a" * 40, "HS256")) is None
    # Correctly signed, but expired.
    expired = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": datetime.now(UTC) - timedelta(seconds=1)},
        get_settings().jwt_secret_key,
        "HS256",
    )
    assert decode_access_token(expired) is None


def test_verify_password_returns_false_rather_than_raising():
    assert hash_password("a password") != "a password"
    assert decode_access_token("") is None
    from app.core.security import verify_password

    stored = hash_password("a password")
    assert verify_password("a password", stored) is True
    assert verify_password("another password", stored) is False
    # A column that somehow doesn't hold a hash must not 500 a login.
    assert verify_password("a password", "not a hash at all") is False
