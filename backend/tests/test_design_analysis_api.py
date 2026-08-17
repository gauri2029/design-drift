"""API tests for /api/v1/projects/{project_id}/design-analysis.

Same mocked-Figma + mocked-Anthropic setup as test_reviews_api.py — no
scan involved here, since the Design Analysis Agent only ever looks at a
project's stored Figma data (see app.services.design_analysis).
"""

import json
from io import BytesIO

import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response
from PIL import Image
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.integrations.storage.local import LocalStorageBackend, get_storage_backend
from app.main import app
from app.models.design_analysis import DesignAnalysis
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
                "name": "Hero",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1400, "height": 900},
                "children": [],
            },
            "styles": {},
        }
    },
}
IMAGES_RESPONSE = {"err": None, "images": {NODE_ID: IMAGE_URL}}

ANALYSIS_RESULT = {
    "layout_summary": "A centered hero section with a heading, subtext, and one CTA button.",
    "design_intent": "Get the visitor to click the primary call-to-action.",
    "key_components": [
        {
            "name": "Primary CTA button",
            "role": "Drives the visitor to convert.",
            "notable_styling": "High-contrast fill, generous padding.",
        }
    ],
    "implementation_risks": ["The heading's exact vertical spacing may be easy to get wrong."],
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


@pytest.fixture(autouse=True)
async def _clean_up():
    yield
    app.dependency_overrides.clear()
    async with async_session_factory() as session:
        await session.execute(delete(DesignAnalysis))
        await session.execute(delete(Project))
        await session.commit()


async def _create_project(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/projects",
        json={
            "name": "Marketing homepage",
            "figma_file_key": FILE_KEY,
            "figma_node_id": NODE_ID,
            "target_url": "https://example.com",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@respx.mock
async def test_design_analysis_lifecycle(monkeypatch, tmp_path) -> None:
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
        return_value=Response(200, content=_png_bytes((1400, 900), (255, 255, 255)))
    )
    anthropic_route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, json=_anthropic_response(ANALYSIS_RESULT))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        project_id = await _create_project(client)

        create_response = await client.post(f"/api/v1/projects/{project_id}/design-analysis")
        assert create_response.status_code == 201, create_response.text
        analysis = create_response.json()

        assert analysis["project_id"] == project_id
        assert analysis["model"] == "claude-opus-5"
        assert analysis["result"]["design_intent"] == ANALYSIS_RESULT["design_intent"]
        assert analysis["result"]["key_components"][0]["name"] == "Primary CTA button"

        list_response = await client.get(f"/api/v1/projects/{project_id}/design-analysis")
        assert list_response.status_code == 200
        assert any(a["id"] == analysis["id"] for a in list_response.json())

    # The rendered Figma image actually reached the model.
    request_body = json.loads(anthropic_route.calls.last.request.content)
    content_blocks = request_body["messages"][0]["content"]
    assert sum(1 for block in content_blocks if block["type"] == "image") == 1


@respx.mock
async def test_design_analysis_returns_502_when_anthropic_key_not_configured(
    monkeypatch, tmp_path
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
        return_value=Response(200, content=_png_bytes((1400, 900), (255, 255, 255)))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        project_id = await _create_project(client)
        response = await client.post(f"/api/v1/projects/{project_id}/design-analysis")

    assert response.status_code == 502
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


async def test_design_analysis_returns_404_when_project_missing() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000/design-analysis"
        )

    assert response.status_code == 404
