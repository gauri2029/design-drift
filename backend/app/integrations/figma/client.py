"""Deterministic HTTP client for the Figma REST API.

No LLM calls here — this only fetches and type-parses Figma's own data
(node tree, styles, rendered image). Judgment about what the design
*means* belongs to a runtime agent consuming this client's output
(Phase 3+), per docs/principles.md #2.
"""

from __future__ import annotations

import httpx

from app.integrations.figma.exceptions import FigmaAPIError, FigmaNodeNotFoundError
from app.integrations.figma.types import FigmaFileNodesResponse, FigmaImagesResponse, FigmaNode


class FigmaClient:
    def __init__(
        self,
        access_token: str,
        base_url: str = "https://api.figma.com/v1",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url,
            headers={"X-Figma-Token": access_token},
            timeout=30.0,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_node(self, file_key: str, node_id: str) -> FigmaNode:
        """Fetch a single node's document tree (styles/layout/hierarchy)."""
        response = await self._client.get(f"/files/{file_key}/nodes", params={"ids": node_id})
        _raise_for_status(response)

        parsed = FigmaFileNodesResponse.model_validate(response.json())
        if parsed.err:
            raise FigmaAPIError(parsed.err)

        container = parsed.nodes.get(node_id)
        if container is None:
            raise FigmaNodeNotFoundError(f"node {node_id!r} not found in file {file_key!r}")
        return container.document

    async def get_image_url(
        self,
        file_key: str,
        node_id: str,
        image_format: str = "png",
        scale: float = 1.0,
    ) -> str:
        """Fetch a render URL for `node_id` (Figma renders it server-side).

        Defaults to scale=1 (CSS-pixel-for-pixel) so the render's dimensions
        are directly comparable to a Playwright screenshot taken with
        device_scale_factor=1, without either side needing to be rescaled
        before pixel-diffing (see app.integrations.imaging.compare_images).
        """
        response = await self._client.get(
            f"/images/{file_key}",
            params={"ids": node_id, "format": image_format, "scale": scale},
        )
        _raise_for_status(response)

        parsed = FigmaImagesResponse.model_validate(response.json())
        if parsed.err:
            raise FigmaAPIError(parsed.err)

        image_url = parsed.images.get(node_id)
        if not image_url:
            raise FigmaNodeNotFoundError(
                f"no rendered image returned for node {node_id!r} in file {file_key!r}"
            )
        return image_url

    async def download_image(self, image_url: str) -> bytes:
        """Download rendered image bytes from a Figma-issued render URL.

        Figma's render URLs point at S3 and are pre-signed, so this is a
        plain unauthenticated GET, not a call against the Figma API itself.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(image_url)
        _raise_for_status(response)
        return response.content


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_error:
        raise FigmaAPIError(
            f"Figma API request failed: {response.status_code} {response.text[:500]}"
        )
