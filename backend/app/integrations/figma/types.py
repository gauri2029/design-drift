"""Typed models for the (small) subset of the Figma REST API we use.

These mirror Figma's own JSON shapes (via a camelCase alias generator) so
`FigmaClient` returns validated Pydantic models, not raw dicts, per
docs/principles.md #7. Only fields Design Drift currently needs for
visual/layout comparison are modeled — Figma's full node schema is much
larger than this.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class FigmaModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class FigmaColor(FigmaModel):
    r: float
    g: float
    b: float
    a: float


class FigmaPaint(FigmaModel):
    type: str
    color: FigmaColor | None = None
    opacity: float | None = None


class FigmaBoundingBox(FigmaModel):
    x: float
    y: float
    width: float
    height: float


class FigmaTextStyle(FigmaModel):
    font_family: str | None = None
    font_weight: float | None = None
    font_size: float | None = None
    line_height_px: float | None = None
    letter_spacing: float | None = None
    text_align_horizontal: str | None = None
    text_align_vertical: str | None = None


class FigmaNode(FigmaModel):
    """A node in a Figma document tree: styles, layout, and children.

    Self-referential via `children` to mirror Figma's recursive tree.
    """

    id: str
    name: str
    type: str
    visible: bool = True

    absolute_bounding_box: FigmaBoundingBox | None = None

    fills: list[FigmaPaint] = []
    strokes: list[FigmaPaint] = []
    stroke_weight: float | None = None
    corner_radius: float | None = None

    # Auto-layout properties (present when layout_mode != "NONE").
    layout_mode: str | None = None
    item_spacing: float | None = None
    padding_left: float | None = None
    padding_right: float | None = None
    padding_top: float | None = None
    padding_bottom: float | None = None
    primary_axis_align_items: str | None = None
    counter_axis_align_items: str | None = None

    # Text nodes only.
    characters: str | None = None
    style: FigmaTextStyle | None = None

    children: list[FigmaNode] = []


class FigmaNodeContainer(FigmaModel):
    document: FigmaNode
    styles: dict[str, object] = {}


class FigmaFileNodesResponse(FigmaModel):
    """Shape of `GET /v1/files/{file_key}/nodes`."""

    name: str
    last_modified: str | None = None
    thumbnail_url: str | None = None
    err: str | None = None
    nodes: dict[str, FigmaNodeContainer | None] = {}


class FigmaImagesResponse(FigmaModel):
    """Shape of `GET /v1/images/{file_key}`."""

    err: str | None = None
    images: dict[str, str | None] = {}
