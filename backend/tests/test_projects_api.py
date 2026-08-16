"""API tests for /api/v1/projects.

These run against the real local Postgres (see backend/README.md — the
same DB used for `uv run uvicorn`), with the Figma HTTP calls mocked via
respx and storage redirected to a temp directory. Rows created during a
test are cleaned up in the `_clean_projects_table` fixture below.
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

FILE_KEY = "abc123"
NODE_ID = "1:23"
IMAGE_URL = "https://figma-alpha-api.s3.amazonaws.com/images/abcd/render.png"

NODES_RESPONSE = {
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
}
IMAGES_RESPONSE = {"err": None, "images": {NODE_ID: IMAGE_URL}}

CREATE_PAYLOAD = {
    "name": "Marketing homepage",
    "figma_file_key": FILE_KEY,
    "figma_node_id": NODE_ID,
    "target_url": "https://example.com",
    "target_selector": "#hero-cta",
}


@pytest.fixture(autouse=True)
async def _clean_up():
    yield
    app.dependency_overrides.clear()
    async with async_session_factory() as session:
        await session.execute(delete(Project))
        await session.commit()


def _mock_figma_endpoints() -> None:
    respx.get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes").mock(
        return_value=Response(200, json=NODES_RESPONSE)
    )
    respx.get(f"https://api.figma.com/v1/images/{FILE_KEY}").mock(
        return_value=Response(200, json=IMAGES_RESPONSE)
    )
    respx.get(IMAGE_URL).mock(return_value=Response(200, content=b"fake-png-bytes"))


@respx.mock
async def test_project_lifecycle(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    _mock_figma_endpoints()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_response = await client.post("/api/v1/projects", json=CREATE_PAYLOAD)
        assert create_response.status_code == 201
        body = create_response.json()
        assert body["name"] == "Marketing homepage"
        assert body["figma_data"]["name"] == "Button"
        assert body["figma_screenshot_key"] is not None
        assert body["target_selector"] == "#hero-cta"
        project_id = body["id"]

        get_response = await client.get(f"/api/v1/projects/{project_id}")
        assert get_response.status_code == 200
        assert get_response.json()["id"] == project_id

        list_response = await client.get("/api/v1/projects")
        assert list_response.status_code == 200
        assert any(p["id"] == project_id for p in list_response.json())

        screenshot_response = await client.get(f"/api/v1/projects/{project_id}/figma/screenshot")
        assert screenshot_response.status_code == 200
        assert screenshot_response.content == b"fake-png-bytes"
        assert screenshot_response.headers["content-type"] == "image/png"


@respx.mock
async def test_create_project_returns_502_when_figma_fetch_fails(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    respx.get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes").mock(
        return_value=Response(403, text="Forbidden")
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/projects", json=CREATE_PAYLOAD)

    assert response.status_code == 502

    async with async_session_factory() as session:
        result = await session.execute(delete(Project))
        await session.commit()
        assert result.rowcount == 0  # nothing should have been persisted


async def test_create_project_returns_502_when_token_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "figma_access_token", "")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/projects", json=CREATE_PAYLOAD)

    assert response.status_code == 502
    assert "FIGMA_ACCESS_TOKEN" in response.json()["detail"]


async def test_get_project_returns_404_when_missing() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
