import pytest
import respx
from httpx import Response

import app.integrations.figma.cache as cache_module
from app.integrations.figma.cache import InMemoryTTLCache
from app.integrations.figma.client import FigmaClient
from app.integrations.figma.exceptions import (
    FigmaAPIError,
    FigmaNodeNotFoundError,
    FigmaRateLimitError,
)

FILE_KEY = "abc123"
NODE_ID = "1:23"

NODES_RESPONSE = {
    "name": "My File",
    "lastModified": "2026-01-01T00:00:00Z",
    "thumbnailUrl": "https://example.com/thumb.png",
    "err": None,
    "nodes": {
        NODE_ID: {
            "document": {
                "id": NODE_ID,
                "name": "Button",
                "type": "FRAME",
                "visible": True,
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 120, "height": 40},
                "fills": [{"type": "SOLID", "color": {"r": 0.2, "g": 0.4, "b": 0.9, "a": 1}}],
                "strokes": [],
                "strokeWeight": 1,
                "cornerRadius": 8,
                "layoutMode": "HORIZONTAL",
                "itemSpacing": 8,
                "paddingLeft": 16,
                "paddingRight": 16,
                "paddingTop": 8,
                "paddingBottom": 8,
                "primaryAxisAlignItems": "CENTER",
                "counterAxisAlignItems": "CENTER",
                "children": [
                    {
                        "id": "1:24",
                        "name": "Label",
                        "type": "TEXT",
                        "characters": "Click me",
                        "style": {
                            "fontFamily": "Inter",
                            "fontWeight": 600,
                            "fontSize": 14,
                            "lineHeightPx": 20,
                            "letterSpacing": 0,
                            "textAlignHorizontal": "CENTER",
                            "textAlignVertical": "CENTER",
                        },
                        "fills": [{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}],
                    }
                ],
            },
            "styles": {},
        }
    },
}

IMAGES_RESPONSE = {
    "err": None,
    "images": {NODE_ID: "https://figma-alpha-api.s3.amazonaws.com/images/abcd/render.png"},
}


@respx.mock
async def test_get_node_parses_document_and_children() -> None:
    route = respx.get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes").mock(
        return_value=Response(200, json=NODES_RESPONSE)
    )
    client = FigmaClient(access_token="token123")

    node = await client.get_node(FILE_KEY, NODE_ID)

    assert route.calls.last.request.headers["X-Figma-Token"] == "token123"
    assert node.name == "Button"
    assert node.layout_mode == "HORIZONTAL"
    assert node.absolute_bounding_box is not None
    assert node.absolute_bounding_box.width == 120
    assert node.fills[0].color is not None
    assert node.fills[0].color.b == 0.9

    assert len(node.children) == 1
    label = node.children[0]
    assert label.characters == "Click me"
    assert label.style is not None
    assert label.style.font_family == "Inter"

    await client.aclose()


@respx.mock
async def test_get_node_raises_on_api_error_field() -> None:
    respx.get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes").mock(
        return_value=Response(200, json={"name": "x", "err": "Invalid token", "nodes": {}})
    )
    client = FigmaClient(access_token="bad-token")

    with pytest.raises(FigmaAPIError, match="Invalid token"):
        await client.get_node(FILE_KEY, NODE_ID)

    await client.aclose()


@respx.mock
async def test_get_node_raises_not_found_when_node_missing() -> None:
    respx.get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes").mock(
        return_value=Response(200, json={"name": "x", "err": None, "nodes": {}})
    )
    client = FigmaClient(access_token="token123")

    with pytest.raises(FigmaNodeNotFoundError):
        await client.get_node(FILE_KEY, NODE_ID)

    await client.aclose()


@respx.mock
async def test_get_node_raises_on_http_error_status() -> None:
    respx.get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes").mock(
        return_value=Response(403, text="Forbidden")
    )
    client = FigmaClient(access_token="token123")

    with pytest.raises(FigmaAPIError, match="403"):
        await client.get_node(FILE_KEY, NODE_ID)

    await client.aclose()


@respx.mock
async def test_get_image_url_returns_render_url() -> None:
    respx.get(f"https://api.figma.com/v1/images/{FILE_KEY}").mock(
        return_value=Response(200, json=IMAGES_RESPONSE)
    )
    client = FigmaClient(access_token="token123")

    url = await client.get_image_url(FILE_KEY, NODE_ID)

    assert url == IMAGES_RESPONSE["images"][NODE_ID]
    await client.aclose()


@respx.mock
async def test_get_image_url_raises_when_missing() -> None:
    respx.get(f"https://api.figma.com/v1/images/{FILE_KEY}").mock(
        return_value=Response(200, json={"err": None, "images": {NODE_ID: None}})
    )
    client = FigmaClient(access_token="token123")

    with pytest.raises(FigmaNodeNotFoundError):
        await client.get_image_url(FILE_KEY, NODE_ID)

    await client.aclose()


@respx.mock
async def test_download_image_returns_bytes() -> None:
    image_url = "https://figma-alpha-api.s3.amazonaws.com/images/abcd/render.png"
    respx.get(image_url).mock(return_value=Response(200, content=b"fake-png-bytes"))
    client = FigmaClient(access_token="token123")

    data = await client.download_image(image_url)

    assert data == b"fake-png-bytes"
    await client.aclose()


@respx.mock
async def test_get_node_uses_cache_on_second_call() -> None:
    route = respx.get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes").mock(
        return_value=Response(200, json=NODES_RESPONSE)
    )
    client = FigmaClient(access_token="token123", cache=InMemoryTTLCache())

    first = await client.get_node(FILE_KEY, NODE_ID)
    second = await client.get_node(FILE_KEY, NODE_ID)

    assert route.call_count == 1  # second call was served from cache
    assert second.name == first.name == "Button"
    await client.aclose()


@respx.mock
async def test_get_node_cache_expires_after_ttl(monkeypatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: now[0])

    route = respx.get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes").mock(
        return_value=Response(200, json=NODES_RESPONSE)
    )
    client = FigmaClient(access_token="token123", cache=InMemoryTTLCache(), cache_ttl_seconds=600)

    await client.get_node(FILE_KEY, NODE_ID)
    assert route.call_count == 1

    now[0] += 601  # past the 10-minute TTL
    await client.get_node(FILE_KEY, NODE_ID)

    assert route.call_count == 2  # cache had expired, so this was a real second call
    await client.aclose()


@respx.mock
async def test_get_image_url_uses_cache_on_second_call() -> None:
    route = respx.get(f"https://api.figma.com/v1/images/{FILE_KEY}").mock(
        return_value=Response(200, json=IMAGES_RESPONSE)
    )
    client = FigmaClient(access_token="token123", cache=InMemoryTTLCache())

    first = await client.get_image_url(FILE_KEY, NODE_ID)
    second = await client.get_image_url(FILE_KEY, NODE_ID)

    assert route.call_count == 1
    assert first == second
    await client.aclose()


@respx.mock
async def test_get_node_raises_rate_limit_error_with_retry_after() -> None:
    respx.get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes").mock(
        return_value=Response(429, headers={"Retry-After": "30"}, text="Too Many Requests")
    )
    client = FigmaClient(access_token="token123", cache=InMemoryTTLCache())

    with pytest.raises(FigmaRateLimitError, match="Figma rate limit reached") as exc_info:
        await client.get_node(FILE_KEY, NODE_ID)

    assert exc_info.value.retry_after_seconds == 30.0
    assert "retry after 30s" in str(exc_info.value)
    await client.aclose()


@respx.mock
async def test_get_node_raises_rate_limit_error_without_retry_after_header() -> None:
    respx.get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes").mock(
        return_value=Response(429, text="Too Many Requests")
    )
    client = FigmaClient(access_token="token123", cache=InMemoryTTLCache())

    with pytest.raises(FigmaRateLimitError) as exc_info:
        await client.get_node(FILE_KEY, NODE_ID)

    assert exc_info.value.retry_after_seconds is None
    assert str(exc_info.value) == "Figma rate limit reached. Please retry shortly."
    await client.aclose()
