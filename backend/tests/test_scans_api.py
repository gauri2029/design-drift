"""API tests for /api/v1/projects/{project_id}/scans.

Runs against the real local Postgres (see test_projects_api.py's module
docstring). The "production app" under test is a local static fixture
page served over a real HTTP server on an ephemeral port — not an
external site (still fully local/deterministic), and not a file:// URL,
since ProjectCreate.target_url requires http(s).
"""

import functools
import http.server
import threading
from io import BytesIO
from pathlib import Path

import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response
from PIL import Image
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.integrations.storage.local import LocalStorageBackend, get_storage_backend
from app.main import app
from app.models.project import Project
from app.models.scan import Scan

FILE_KEY = "abc123"
NODE_ID = "1:23"
IMAGE_URL = "https://figma-alpha-api.s3.amazonaws.com/images/abcd/render.png"
FIXTURES_DIR = Path(__file__).parent / "fixtures"

NODES_RESPONSE = {
    "name": "My File",
    "err": None,
    "nodes": {
        NODE_ID: {
            "document": {
                "id": NODE_ID,
                "name": "Card",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 200, "height": 100},
                "children": [],
            },
            "styles": {},
        }
    },
}
IMAGES_RESPONSE = {"err": None, "images": {NODE_ID: IMAGE_URL}}


def _png_bytes(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(scope="module")
def fixture_server():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(FIXTURES_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    thread.join()


@pytest.fixture(autouse=True)
async def _clean_up():
    yield
    app.dependency_overrides.clear()
    async with async_session_factory() as session:
        await session.execute(delete(Scan))
        await session.execute(delete(Project))
        await session.commit()


def _mock_figma_endpoints(expected_image: bytes) -> None:
    respx.get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes").mock(
        return_value=Response(200, json=NODES_RESPONSE)
    )
    respx.get(f"https://api.figma.com/v1/images/{FILE_KEY}").mock(
        return_value=Response(200, json=IMAGES_RESPONSE)
    )
    respx.get(IMAGE_URL).mock(return_value=Response(200, content=expected_image))


async def _create_project(
    client: AsyncClient,
    fixture_server: http.server.ThreadingHTTPServer,
    *,
    selector: str | None = "#card",
) -> dict:
    host, port = fixture_server.server_address[:2]
    payload = {
        "name": "Card component",
        "figma_file_key": FILE_KEY,
        "figma_node_id": NODE_ID,
        "target_url": f"http://{host}:{port}/capture_fixture.html",
        "target_selector": selector,
    }
    response = await client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@respx.mock
async def test_scan_lifecycle_with_matching_screenshot(
    monkeypatch, tmp_path, fixture_server
) -> None:
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    # The fixture's #card element is a solid red 200x100 box.
    _mock_figma_endpoints(_png_bytes((200, 100), (255, 0, 0)))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        project = await _create_project(client, fixture_server)
        project_id = project["id"]

        create_response = await client.post(f"/api/v1/projects/{project_id}/scans", json={})
        assert create_response.status_code == 201, create_response.text
        scan = create_response.json()

        assert scan["comparison_result"]["dimensions_match"] is True
        assert scan["comparison_result"]["mismatch_percentage"] == 0.0
        assert scan["breakpoint"] is None
        assert "violations" in scan["accessibility_report"]
        scan_id = scan["id"]

        get_response = await client.get(f"/api/v1/projects/{project_id}/scans/{scan_id}")
        assert get_response.status_code == 200
        assert get_response.json()["id"] == scan_id

        list_response = await client.get(f"/api/v1/projects/{project_id}/scans")
        assert list_response.status_code == 200
        assert any(s["id"] == scan_id for s in list_response.json())

        production_response = await client.get(
            f"/api/v1/projects/{project_id}/scans/{scan_id}/production"
        )
        assert production_response.status_code == 200
        assert production_response.headers["content-type"] == "image/png"
        assert Image.open(BytesIO(production_response.content)).size == (200, 100)

        diff_response = await client.get(f"/api/v1/projects/{project_id}/scans/{scan_id}/diff")
        assert diff_response.status_code == 200
        assert diff_response.headers["content-type"] == "image/png"


@respx.mock
async def test_scan_reports_mismatch_for_different_colors(
    monkeypatch, tmp_path, fixture_server
) -> None:
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    # Figma expects blue; the fixture's #card is actually red.
    _mock_figma_endpoints(_png_bytes((200, 100), (0, 0, 255)))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        project = await _create_project(client, fixture_server)
        create_response = await client.post(f"/api/v1/projects/{project['id']}/scans", json={})

    assert create_response.status_code == 201
    result = create_response.json()["comparison_result"]
    assert result["dimensions_match"] is True
    assert result["mismatch_percentage"] == 100.0


@respx.mock
async def test_scan_returns_502_when_selector_not_found(
    monkeypatch, tmp_path, fixture_server
) -> None:
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    _mock_figma_endpoints(_png_bytes((200, 100), (255, 0, 0)))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        project = await _create_project(client, fixture_server, selector="#does-not-exist")
        create_response = await client.post(f"/api/v1/projects/{project['id']}/scans", json={})

    assert create_response.status_code == 502


async def test_scan_returns_404_when_project_missing() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000/scans", json={}
        )

    assert response.status_code == 404


@respx.mock
async def test_scan_at_named_breakpoint_uses_its_viewport(
    monkeypatch, tmp_path, fixture_server
) -> None:
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    _mock_figma_endpoints(_png_bytes((200, 100), (255, 0, 0)))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        project = await _create_project(client, fixture_server)
        create_response = await client.post(
            f"/api/v1/projects/{project['id']}/scans", json={"breakpoint": "mobile"}
        )

    assert create_response.status_code == 201, create_response.text
    scan = create_response.json()
    assert scan["breakpoint"] == "mobile"
    assert (scan["viewport_width"], scan["viewport_height"]) == (375, 667)


async def test_scan_create_rejects_unknown_breakpoint() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000/scans",
            json={"breakpoint": "ultra-wide"},
        )

    assert response.status_code == 422


@respx.mock
async def test_create_scans_at_all_breakpoints_returns_one_scan_per_breakpoint(
    monkeypatch, tmp_path, fixture_server
) -> None:
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-token")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)
    _mock_figma_endpoints(_png_bytes((200, 100), (255, 0, 0)))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        project = await _create_project(client, fixture_server)
        response = await client.post(f"/api/v1/projects/{project['id']}/scans/breakpoints")

    assert response.status_code == 201, response.text
    scans = response.json()
    assert {scan["breakpoint"] for scan in scans} == {"mobile", "tablet", "desktop"}
