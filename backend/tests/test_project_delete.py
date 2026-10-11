"""Deleting a project removes its rows *and* its files.

The rows cascade on their own; the files are what this has to get right.
A project that leaves its screenshots and a cloned checkout behind is a
slow disk leak nothing will ever clean up, because the row naming them is
gone.
"""

import uuid

import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.integrations.storage.local import LocalStorageBackend, get_storage_backend
from app.main import app
from app.models.design_analysis import DesignAnalysis
from app.models.project import Project
from app.models.user import User
from app.services.workspace import workspace_for

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
                "name": "F",
                "err": None,
                "nodes": {
                    NODE_ID: {
                        "document": {
                            "id": NODE_ID,
                            "name": "Button",
                            "type": "FRAME",
                            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1, "height": 1},
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


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _signup(http: AsyncClient, email: str) -> dict[str, str]:
    response = await http.post(
        "/api/v1/auth/signup",
        json={"email": email, "name": email.split("@")[0], "password": "a good long password"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@respx.mock
async def test_deleting_removes_the_project_and_its_screenshot(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    _mock_figma()

    async with _client() as http:
        alice = await _signup(http, "alice@example.com")
        created = await http.post("/api/v1/projects", json=CREATE_PAYLOAD, headers=alice)
        project_id = created.json()["id"]
        screenshot = tmp_path / created.json()["figma_screenshot_key"]
        assert screenshot.exists()

        response = await http.delete(f"/api/v1/projects/{project_id}", headers=alice)

        assert response.status_code == 204
        assert (await http.get(f"/api/v1/projects/{project_id}", headers=alice)).status_code == 404
        assert (await http.get("/api/v1/projects", headers=alice)).json() == []

    # The file, not just the row.
    assert not screenshot.exists()


@respx.mock
async def test_analyses_go_with_the_project(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    _mock_figma()

    async with _client() as http:
        alice = await _signup(http, "alice@example.com")
        project_id = (
            await http.post("/api/v1/projects", json=CREATE_PAYLOAD, headers=alice)
        ).json()["id"]

        production = f"design-analyses/{uuid.uuid4()}/production.png"
        (tmp_path / production).parent.mkdir(parents=True)
        (tmp_path / production).write_bytes(b"png")
        async with async_session_factory() as session:
            session.add(
                DesignAnalysis(
                    project_id=uuid.UUID(project_id),
                    model="test",
                    result={},
                    production_screenshot_key=production,
                )
            )
            await session.commit()

        assert (
            await http.delete(f"/api/v1/projects/{project_id}", headers=alice)
        ).status_code == 204

    async with async_session_factory() as session:
        remaining = (
            await session.execute(select(func.count()).select_from(DesignAnalysis))
        ).scalar()
    assert remaining == 0
    # A run's screenshots are the bulk of what a project puts on disk.
    assert not (tmp_path / production).exists()


@respx.mock
async def test_a_cloned_workspace_is_removed(monkeypatch, tmp_path):
    """Third-party source must not survive the project that cloned it."""
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    monkeypatch.setattr(get_settings(), "workspace_root", str(tmp_path / "ws"))
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    _mock_figma()

    async with _client() as http:
        alice = await _signup(http, "alice@example.com")
        project_id = (
            await http.post("/api/v1/projects", json=CREATE_PAYLOAD, headers=alice)
        ).json()["id"]

        checkout = workspace_for(uuid.UUID(project_id), uuid.uuid4())
        checkout.mkdir(parents=True)
        (checkout / "index.html").write_text("<p>someone else's code</p>")

        assert (
            await http.delete(f"/api/v1/projects/{project_id}", headers=alice)
        ).status_code == 204

    assert not checkout.exists()
    assert not checkout.parent.exists()


@respx.mock
async def test_another_account_cannot_delete_your_project(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    _mock_figma()

    async with _client() as http:
        alice = await _signup(http, "alice@example.com")
        bob = await _signup(http, "bob@example.com")
        project_id = (
            await http.post("/api/v1/projects", json=CREATE_PAYLOAD, headers=alice)
        ).json()["id"]

        response = await http.delete(f"/api/v1/projects/{project_id}", headers=bob)

        # 404, not 403 — and crucially the project must still be there.
        assert response.status_code == 404
        assert (await http.get(f"/api/v1/projects/{project_id}", headers=alice)).status_code == 200


async def test_deleting_requires_authentication():
    async with _client() as http:
        response = await http.delete(f"/api/v1/projects/{uuid.uuid4()}")
    assert response.status_code == 401


@respx.mock
async def test_a_missing_artifact_does_not_block_the_delete(monkeypatch, tmp_path):
    """A run that failed midway can record a key whose file was never
    written. The project must still delete."""
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    _mock_figma()

    async with _client() as http:
        alice = await _signup(http, "alice@example.com")
        created = await http.post("/api/v1/projects", json=CREATE_PAYLOAD, headers=alice)
        project_id = created.json()["id"]

        (tmp_path / created.json()["figma_screenshot_key"]).unlink()

        assert (
            await http.delete(f"/api/v1/projects/{project_id}", headers=alice)
        ).status_code == 204
