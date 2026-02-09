from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias, Union


GeometryKind = Literal["points", "lines", "polygons"]


@dataclass(frozen=True)
class PointFeature:
    id: str
    lon: float
    lat: float
    props: dict[str, Any]


@dataclass(frozen=True)
class LineFeature:
    id: str
    coords: list[tuple[float, float]]  # [(lon, lat), ...]
    props: dict[str, Any]


@dataclass(frozen=True)
class PolygonFeature:
    id: str
    rings: list[
        list[tuple[float, float]]
    ]  # [outer_ring, ...]; each ring is [(lon, lat), ...]
    props: dict[str, Any]


LayerFeature: TypeAlias = Union[PointFeature, LineFeature, PolygonFeature]


@dataclass(frozen=True)
class Layer:
    """
    A scenario-defined layer (points/lines/polygons) with a stable id.

    All scenario-specific semantics (titles, styling, routing roles) should live in YAML;
    this type intentionally stays generic.
    """

    id: str
    kind: GeometryKind
    title: str
    features: list[LayerFeature]
    # Free-form style hints (e.g. colors/widths) consumed by the Plotly builder.
    style: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LayerBundle:
    layers: list[Layer]

    def get(self, layer_id: str) -> Layer | None:
        lid = (layer_id or "").strip()
        for layer in self.layers:
            if layer.id == lid:
                return layer
        return None

    def of_kind(self, kind: GeometryKind) -> list[Layer]:
        return [layer for layer in self.layers if layer.kind == kind]
