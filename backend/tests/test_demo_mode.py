"""The public demo's read-only guarantee.

Two properties, both enforced server-side and both tested by trying to
break them rather than by reading the code:

1. An anonymous visitor can *read* the showcase account's projects and runs,
   so the deployed app is browsable without a signup.
2. An anonymous visitor, and any signed-in stranger, is refused every action
   that would spend money or change what the demo shows.

Property 2 is the one that matters. If it regresses, a crawler hitting the
public URL spends the owner's API budget, so each guarded route is listed
explicitly below: a new cost-bearing route that forgets the guard will not
be covered by a generic assertion, so the list is the test.

Uses real requests through the real dependencies (no conftest override):
the override exists for tests that don't care who they are, and identity is
exactly what these are about.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.main import app
from app.models.design_analysis import DesignAnalysis
from app.models.project import Project
from app.models.user import User
from app.services import rate_limit

pytestmark = pytest.mark.anonymous

DEMO_EMAIL = "demo-fixture@example.com"

# A body that passes FixReviewRequest validation (decisions has
# min_length=1), so a request reaches the demo guard instead of being
# turned back as a 422 — which would make the assertion pass for the
# wrong reason.
VALID_REVIEW = {"decisions": [{"finding_title": "t", "decision": "approved"}]}


@pytest.fixture(autouse=True)
async def _clean_up():
    rate_limit.reset()
    yield
    app.dependency_overrides.clear()
    rate_limit.reset()
    async with async_session_factory() as session:
        await session.execute(delete(Project))
        await session.execute(delete(User))
        await session.commit()


@pytest.fixture
def demo_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "demo_user_email", DEMO_EMAIL)
    return settings


async def _seed_demo() -> tuple[User, Project, DesignAnalysis]:
    """A showcase account holding one project with one finished run."""
    async with async_session_factory() as session:
        user = User(email=DEMO_EMAIL, name="Design Drift Demo", password_hash="x")
        session.add(user)
        await session.flush()

        project = Project(
            owner_id=user.id,
            name="Recipes Gallery",
            figma_file_key="demo-file",
            figma_node_id="1:2",
            target_url="https://recipes-gallery.example.com",
        )
        session.add(project)
        await session.flush()

        analysis = DesignAnalysis(
            project_id=project.id,
            model="demo",
            result={"layout_summary": "s", "design_intent": "i", "key_components": [],
                    "implementation_risks": []},
            aggregated_findings={"problems_found": True, "findings": []},
        )
        session.add(analysis)
        await session.commit()
        await session.refresh(user)
        await session.refresh(project)
        await session.refresh(analysis)
        return user, project, analysis


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# --- Property 1: the demo is readable without a signup --------------------


async def test_anonymous_can_list_the_demo_projects(demo_settings):
    _, project, _ = await _seed_demo()

    async with _client() as client:
        response = await client.get("/api/v1/projects")

    assert response.status_code == 200
    assert [row["name"] for row in response.json()] == [project.name]


async def test_anonymous_can_read_a_demo_run(demo_settings):
    _, project, analysis = await _seed_demo()

    async with _client() as client:
        response = await client.get(f"/api/v1/projects/{project.id}/design-analysis")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [str(analysis.id)]


async def test_demo_status_reports_enabled_and_seeded(demo_settings):
    async with _client() as client:
        before = await client.get("/api/v1/demo/status")
        assert before.json() == {"enabled": True, "seeded": False, "user_name": None}

        await _seed_demo()
        after = await client.get("/api/v1/demo/status")

    assert after.json() == {
        "enabled": True,
        "seeded": True,
        "user_name": "Design Drift Demo",
    }


# --- Property 2: nothing costly or mutating is reachable ------------------
#
# Every route that spends money (a browser launch, an LLM call) or rewrites
# a stored run. Listed one by one on purpose: see this module's docstring.


async def test_anonymous_cannot_start_a_run(demo_settings):
    _, project, _ = await _seed_demo()

    async with _client() as client:
        plain = await client.post(f"/api/v1/projects/{project.id}/design-analysis")
        streamed = await client.post(f"/api/v1/projects/{project.id}/design-analysis/stream")

    # 403, not 401: the caller was legitimately resolved to the demo
    # account, and the refusal is about the action, not the identity. The
    # message has to explain the demo, since a recruiter reads it.
    assert plain.status_code == 403
    assert streamed.status_code == 403
    assert "read-only demo" in plain.json()["detail"]


async def test_anonymous_cannot_run_a_scan_or_review(demo_settings):
    _, project, _ = await _seed_demo()

    async with _client() as client:
        scan = await client.post(f"/api/v1/projects/{project.id}/scans")
        breakpoints = await client.post(f"/api/v1/projects/{project.id}/scans/breakpoints")

    assert scan.status_code == 403
    assert breakpoints.status_code == 403


async def test_anonymous_cannot_review_apply_or_verify(demo_settings):
    _, project, analysis = await _seed_demo()
    base = f"/api/v1/projects/{project.id}/design-analysis/{analysis.id}"

    async with _client() as client:
        review = await client.put(f"{base}/fix-review", json=VALID_REVIEW)
        applied = await client.post(f"{base}/apply")
        verified = await client.post(f"{base}/verify", json={"target_url": None})

    assert review.status_code == 403
    assert applied.status_code == 403
    assert verified.status_code == 403


async def test_anonymous_cannot_delete_the_demo_project(demo_settings):
    _, project, _ = await _seed_demo()

    async with _client() as client:
        response = await client.delete(f"/api/v1/projects/{project.id}")

    assert response.status_code == 403

    # And it is really still there — a 403 that deleted anyway would pass
    # the assertion above.
    async with async_session_factory() as session:
        assert await session.get(Project, project.id) is not None


async def test_anonymous_cannot_create_a_project(demo_settings):
    """Creating stays 401: an anonymous caller has no account to own it.

    Not 403, because this is not the demo-gate refusing an action on the
    showcase — it is the ordinary "writes need a token" rule, which the
    demo resolution deliberately does not relax.
    """
    await _seed_demo()

    async with _client() as client:
        response = await client.post(
            "/api/v1/projects",
            json={
                "name": "mine",
                "figma_file_key": "k",
                "figma_node_id": "1:1",
                "target_url": "https://example.com",
            },
        )

    assert response.status_code == 401


async def test_a_signed_in_stranger_cannot_touch_the_demo(demo_settings):
    """The gate keys on the project's owner, not on the caller.

    A real account that guessed the demo project's id must be refused too:
    otherwise anyone could sign up and burn the owner's API budget on the
    showcase, which is exactly what the demo lock exists to prevent.
    """
    _, project, _ = await _seed_demo()

    async with _client() as client:
        signup = await client.post(
            "/api/v1/auth/signup",
            json={
                "name": "Stranger",
                "email": "stranger@example.com",
                "password": "pw-long-enough",
            },
        )
        assert signup.status_code == 201
        token = signup.json()["access_token"]

        response = await client.post(
            f"/api/v1/projects/{project.id}/design-analysis",
            headers={"Authorization": f"Bearer {token}"},
        )

    # 404: a stranger does not own it, so ownership refuses first and the
    # project's existence is not confirmed. Either refusal is correct here;
    # what must never happen is a run starting.
    assert response.status_code == 404


# --- The gate is off by default -------------------------------------------


async def test_without_demo_mode_anonymous_reads_are_rejected(monkeypatch):
    """A local checkout behaves exactly as before: no token means 401.

    `demo_user_email` is pinned to the seeded address even though demo mode
    is off, so the 401 can only come from the flag being respected. Without
    the pin, the lookup would miss because no row matches the default
    address, and this test would pass even if the flag were ignored
    entirely.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "demo_user_email", DEMO_EMAIL)
    monkeypatch.setattr(settings, "demo_mode", False)
    await _seed_demo()  # the row exists, and the address matches

    async with _client() as client:
        response = await client.get("/api/v1/projects")

    assert response.status_code == 401


async def test_demo_mode_without_a_seed_is_not_a_demo(monkeypatch):
    """Switched on but unseeded serves a normal app, not a 500."""
    settings = get_settings()
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "demo_user_email", DEMO_EMAIL)

    async with _client() as client:
        status = await client.get("/api/v1/demo/status")
        projects = await client.get("/api/v1/projects")

    assert status.json()["seeded"] is False
    assert projects.status_code == 401


async def test_demo_owned_project_is_writable_when_demo_mode_is_off(monkeypatch):
    """The lock follows the flag, not the email address.

    Without this, turning demo mode off would leave a deployment unable to
    manage the account it had seeded.
    """
    from app.services import demo as demo_service

    _, project, _ = await _seed_demo()
    settings = get_settings()
    monkeypatch.setattr(settings, "demo_mode", False)

    async with async_session_factory() as session:
        fresh = await session.get(Project, project.id)
        assert fresh is not None
        # Does not raise.
        await demo_service.guard_mutation(session, fresh, "anything")


# --- Signup throttling ----------------------------------------------------


async def test_signup_is_rate_limited_per_address(monkeypatch):
    """The one unauthenticated write a public deployment exposes."""
    settings = get_settings()
    monkeypatch.setattr(settings, "signup_rate_limit_per_hour", 2)

    async with _client() as client:
        first = await client.post(
            "/api/v1/auth/signup",
            json={"name": "A", "email": "a@example.com", "password": "pw-long-enough"},
        )
        second = await client.post(
            "/api/v1/auth/signup",
            json={"name": "B", "email": "b@example.com", "password": "pw-long-enough"},
        )
        third = await client.post(
            "/api/v1/auth/signup",
            json={"name": "C", "email": "c@example.com", "password": "pw-long-enough"},
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert third.status_code == 429


async def test_the_showcase_address_cannot_be_claimed(demo_settings):
    """Signing up as the demo account would grant write access to it."""
    async with _client() as client:
        response = await client.post(
            "/api/v1/auth/signup",
            json={"name": "Impostor", "email": DEMO_EMAIL, "password": "pw-long-enough"},
        )

    assert response.status_code == 409
    # Same wording as a genuinely taken address, so this does not become a
    # way to discover which address the deployment uses for its demo.
    assert response.json()["detail"] == "an account with that email already exists"


async def test_the_showcase_address_check_ignores_case(demo_settings):
    async with _client() as client:
        response = await client.post(
            "/api/v1/auth/signup",
            json={"name": "Impostor", "email": DEMO_EMAIL.upper(), "password": "pw-long-enough"},
        )

    assert response.status_code == 409


async def test_mutating_routes_still_require_a_token_with_demo_mode_off(monkeypatch):
    """The regression this guards against is the serious one.

    The mutating routes depend on `current_user_or_demo` so an anonymous
    visitor gets an explanatory 403 instead of a bare 401. That dependency
    must not become a way to run the agents without an account when the
    deployment is *not* a demo — which is every private deployment and
    every local checkout.

    Demo mode is off here, with `demo_user_email` pinned to the seeded
    address so the refusal can only come from the flag — see the sibling
    read test for why that pin matters.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "demo_user_email", DEMO_EMAIL)
    monkeypatch.setattr(settings, "demo_mode", False)

    _, project, analysis = await _seed_demo()
    base = f"/api/v1/projects/{project.id}/design-analysis/{analysis.id}"

    async with _client() as client:
        attempts = {
            "run": await client.post(f"/api/v1/projects/{project.id}/design-analysis"),
            "stream": await client.post(f"/api/v1/projects/{project.id}/design-analysis/stream"),
            "scan": await client.post(f"/api/v1/projects/{project.id}/scans"),
            "breakpoints": await client.post(f"/api/v1/projects/{project.id}/scans/breakpoints"),
            "fix-review": await client.put(f"{base}/fix-review", json=VALID_REVIEW),
            "apply": await client.post(f"{base}/apply"),
            "verify": await client.post(f"{base}/verify", json={"target_url": None}),
            "delete": await client.delete(f"/api/v1/projects/{project.id}"),
        }

    assert {name: response.status_code for name, response in attempts.items()} == {
        "run": 401,
        "stream": 401,
        "scan": 401,
        "breakpoints": 401,
        "fix-review": 401,
        "apply": 401,
        "verify": 401,
        "delete": 401,
    }

    # And the project survived the delete attempt.
    async with async_session_factory() as session:
        assert await session.get(Project, project.id) is not None


async def test_demo_images_stay_readable_anonymously(demo_settings):
    """The screenshots and diffs are the demo.

    Guards against a real slip made while building this: the demo gate was
    applied to a GET image route, which would have made the showcase 403 on
    its own screenshots while still looking fine in every other test. These
    routes must stay readable without a token.

    404 is the pass condition here, not 200: the seeded run in this module
    carries no stored image bytes. What matters is that the *authorization*
    layer let the request through to the lookup instead of refusing it.
    """
    _, project, analysis = await _seed_demo()
    base = f"/api/v1/projects/{project.id}/design-analysis/{analysis.id}"

    async with _client() as client:
        statuses = {
            "production": (await client.get(f"{base}/production")).status_code,
            "diff": (await client.get(f"{base}/diff")).status_code,
            "verification": (await client.get(f"{base}/verification-production")).status_code,
            "verification-diff": (await client.get(f"{base}/verification-diff")).status_code,
            "figma": (
                await client.get(f"/api/v1/projects/{project.id}/figma/screenshot")
            ).status_code,
        }

    assert 403 not in statuses.values(), statuses
    assert 401 not in statuses.values(), statuses
