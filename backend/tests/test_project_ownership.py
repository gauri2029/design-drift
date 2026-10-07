"""Cross-user access to projects.

Deliberately uses real tokens against the real `require_current_user`
rather than conftest's override: the override is a convenience for tests
that don't care who they are, and isolation is precisely the thing it would
paper over. Two accounts are created through the API, and each one's token
is used to try to reach the other's project.

Every cross-user attempt must be a 404, not a 403. A 403 says "this exists,
you can't have it", which tells someone holding a guessed UUID that they
guessed a real project.
"""

import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.integrations.storage.local import LocalStorageBackend, get_storage_backend
from app.main import app
from app.models.project import Project
from app.models.user import User

pytestmark = pytest.mark.anonymous

FILE_KEY = "abc123"
NODE_ID = "1:23"
IMAGE_URL = "https://figma-alpha-api.s3.amazonaws.com/images/abcd/render.png"

CREATE_PAYLOAD = {
    "name": "Marketing homepage",
    "figma_file_key": FILE_KEY,
    "figma_node_id": NODE_ID,
    "target_url": "https://example.com",
}


@pytest.fixture(autouse=True)
async def _clean_up():
    yield
    app.dependency_overrides.clear()
    async with async_session_factory() as session:
        await session.execute(delete(Project))
        await session.execute(delete(User))
        await session.commit()


def _mock_figma() -> None:
    respx.get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes").mock(
        return_value=Response(
            200,
            json={
                "name": "My File",
                "err": None,
                "nodes": {
                    NODE_ID: {
                        "document": {
                            "id": NODE_ID,
                            "name": "Button",
                            "type": "FRAME",
                            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 120, "height": 40},
                            "children": [],
                        },
                        "styles": {},
                    }
                },
            },
        )
    )
    respx.get(f"https://api.figma.com/v1/images/{FILE_KEY}").mock(
        return_value=Response(200, json={"err": None, "images": {NODE_ID: IMAGE_URL}})
    )
    respx.get(IMAGE_URL).mock(return_value=Response(200, content=b"fake-png-bytes"))


async def _signup(client: AsyncClient, email: str) -> dict[str, str]:
    """An account, and the header that authenticates as it."""
    response = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "name": email.split("@")[0], "password": "a good long password"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@respx.mock
async def test_a_project_is_only_listed_for_the_account_that_made_it(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    _mock_figma()

    async with _client() as client:
        alice = await _signup(client, "alice@example.com")
        bob = await _signup(client, "bob@example.com")

        created = await client.post("/api/v1/projects", json=CREATE_PAYLOAD, headers=alice)
        assert created.status_code == 201
        project_id = created.json()["id"]

        assert [p["id"] for p in (await client.get("/api/v1/projects", headers=alice)).json()] == [
            project_id
        ]
        # Not "a different ordering" or "filtered in the UI" — Bob's list is
        # empty because the query never selected it.
        assert (await client.get("/api/v1/projects", headers=bob)).json() == []


@respx.mock
async def test_another_account_cannot_read_the_project_or_its_screenshot(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    _mock_figma()

    async with _client() as client:
        alice = await _signup(client, "alice@example.com")
        bob = await _signup(client, "bob@example.com")
        project_id = (
            await client.post("/api/v1/projects", json=CREATE_PAYLOAD, headers=alice)
        ).json()["id"]

        for path in (
            f"/api/v1/projects/{project_id}",
            f"/api/v1/projects/{project_id}/figma/screenshot",
        ):
            assert (await client.get(path, headers=alice)).status_code == 200, path
            # 404, not 403: a 403 would confirm the id is real.
            assert (await client.get(path, headers=bob)).status_code == 404, path


@respx.mock
async def test_another_account_cannot_scan_or_analyze_someone_elses_project(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    _mock_figma()

    async with _client() as client:
        alice = await _signup(client, "alice@example.com")
        bob = await _signup(client, "bob@example.com")
        project_id = (
            await client.post("/api/v1/projects", json=CREATE_PAYLOAD, headers=alice)
        ).json()["id"]

        # The expensive, side-effecting routes matter most: these spend
        # money and write to a checkout.
        for method, path in (
            ("GET", f"/api/v1/projects/{project_id}/scans"),
            ("POST", f"/api/v1/projects/{project_id}/scans"),
            ("GET", f"/api/v1/projects/{project_id}/design-analysis"),
            ("POST", f"/api/v1/projects/{project_id}/design-analysis"),
        ):
            response = await client.request(method, path, headers=bob)
            assert response.status_code == 404, f"{method} {path} -> {response.status_code}"


@respx.mock
async def test_every_project_route_refuses_an_unauthenticated_request(monkeypatch, tmp_path):
    """No project route may be reachable without a token at all."""
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    _mock_figma()

    async with _client() as client:
        alice = await _signup(client, "alice@example.com")
        project_id = (
            await client.post("/api/v1/projects", json=CREATE_PAYLOAD, headers=alice)
        ).json()["id"]

        for method, path in (
            ("GET", "/api/v1/projects"),
            ("POST", "/api/v1/projects"),
            ("GET", f"/api/v1/projects/{project_id}"),
            ("GET", f"/api/v1/projects/{project_id}/figma/screenshot"),
            ("GET", f"/api/v1/projects/{project_id}/scans"),
            ("GET", f"/api/v1/projects/{project_id}/design-analysis"),
        ):
            response = await client.request(method, path)
            assert response.status_code == 401, f"{method} {path} -> {response.status_code}"


@respx.mock
async def test_deleting_an_account_takes_its_projects_with_it(monkeypatch, tmp_path):
    """The FK cascade, asserted — an orphaned project would be unreachable
    but still occupy the Figma file key and the storage it wrote."""
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    _mock_figma()

    async with _client() as client:
        alice = await _signup(client, "alice@example.com")
        await client.post("/api/v1/projects", json=CREATE_PAYLOAD, headers=alice)

    async with async_session_factory() as session:
        await session.execute(delete(User).where(User.email == "alice@example.com"))
        await session.commit()
        remaining = (await session.execute(delete(Project).returning(Project.id))).all()
        await session.commit()

    assert remaining == []
