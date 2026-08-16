"""API tests for /api/v1/projects/{project_id}/scans/{scan_id}/reviews.

Same local-fixture-server setup as test_scans_api.py, plus a mocked
Anthropic Messages API response (see test_llm_client.py for why mocking
the raw HTTP layer is the right level here).
"""

import functools
import http.server
import json
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
from app.models.review import Review
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

REVIEW_RESULT = {
    "material_drift_detected": True,
    "summary": "The call-to-action button is visibly narrower in production than in Figma.",
    "findings": [
        {
            "category": "spacing",
            "severity": "major",
            "title": "Button is narrower than designed",
            "description": "Figma shows a 200x100 button; production renders it narrower.",
            "evidence": "The diff image highlights a vertical strip along the button's edge.",
            "likely_area": "the primary call-to-action button",
        }
    ],
}


def _png_bytes(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _anthropic_response(parsed_json: dict) -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5",
        "content": [{"type": "text", "text": json.dumps(parsed_json)}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


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
        await session.execute(delete(Review))
        await session.execute(delete(Scan))
        await session.execute(delete(Project))
        await session.commit()


async def _create_project_and_scan(
    client: AsyncClient, fixture_server: http.server.ThreadingHTTPServer
) -> tuple[str, str]:
    host, port = fixture_server.server_address[:2]
    project_response = await client.post(
        "/api/v1/projects",
        json={
            "name": "Card component",
            "figma_file_key": FILE_KEY,
            "figma_node_id": NODE_ID,
            "target_url": f"http://{host}:{port}/capture_fixture.html",
            "target_selector": "#card",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]

    scan_response = await client.post(f"/api/v1/projects/{project_id}/scans", json={})
    assert scan_response.status_code == 201, scan_response.text
    return project_id, scan_response.json()["id"]


@respx.mock
async def test_review_lifecycle(monkeypatch, tmp_path, fixture_server) -> None:
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-figma-token")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-anthropic-key")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)

    respx.get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes").mock(
        return_value=Response(200, json=NODES_RESPONSE)
    )
    respx.get(f"https://api.figma.com/v1/images/{FILE_KEY}").mock(
        return_value=Response(200, json=IMAGES_RESPONSE)
    )
    respx.get(IMAGE_URL).mock(
        return_value=Response(200, content=_png_bytes((200, 100), (255, 0, 0)))
    )
    anthropic_route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, json=_anthropic_response(REVIEW_RESULT))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        project_id, scan_id = await _create_project_and_scan(client, fixture_server)

        create_response = await client.post(
            f"/api/v1/projects/{project_id}/scans/{scan_id}/reviews"
        )
        assert create_response.status_code == 201, create_response.text
        review = create_response.json()

        assert review["scan_id"] == scan_id
        assert review["model"] == "claude-opus-5"
        assert review["result"]["material_drift_detected"] is True
        assert review["result"]["findings"][0]["category"] == "spacing"

        list_response = await client.get(f"/api/v1/projects/{project_id}/scans/{scan_id}/reviews")
        assert list_response.status_code == 200
        assert any(r["id"] == review["id"] for r in list_response.json())

    # The request actually sent to Claude carries all three images.
    request_body = json.loads(anthropic_route.calls.last.request.content)
    content_blocks = request_body["messages"][0]["content"]
    assert sum(1 for block in content_blocks if block["type"] == "image") == 3


@respx.mock
async def test_review_returns_502_when_anthropic_key_not_configured(
    monkeypatch, tmp_path, fixture_server
) -> None:
    monkeypatch.setattr(get_settings(), "figma_access_token", "test-figma-token")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    app.dependency_overrides[get_storage_backend] = lambda: LocalStorageBackend(root=tmp_path)

    respx.get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes").mock(
        return_value=Response(200, json=NODES_RESPONSE)
    )
    respx.get(f"https://api.figma.com/v1/images/{FILE_KEY}").mock(
        return_value=Response(200, json=IMAGES_RESPONSE)
    )
    respx.get(IMAGE_URL).mock(
        return_value=Response(200, content=_png_bytes((200, 100), (255, 0, 0)))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        project_id, scan_id = await _create_project_and_scan(client, fixture_server)
        response = await client.post(f"/api/v1/projects/{project_id}/scans/{scan_id}/reviews")

    assert response.status_code == 502
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


async def test_review_returns_404_when_scan_missing() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000"
            "/scans/00000000-0000-0000-0000-000000000000/reviews"
        )

    assert response.status_code == 404
