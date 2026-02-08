from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


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
    rings: list[list[tuple[float, float]]]  # [outer_ring, ...]; each ring is [(lon, lat), ...]
    props: dict[str, Any]


@dataclass(frozen=True)
class PragueLayers:
    flood_q100: list[PolygonFeature]
    metro_ways: list[LineFeature]
    beer_pois: list[PointFeature]
    # Realistically, "near metro" means near a station/entrance, not the track geometry.
    metro_stations: list[PointFeature] = field(default_factory=list)
    # Optional tram layers to keep the demo small but more realistic.
    tram_ways: list[LineFeature] = field(default_factory=list)
    tram_stops: list[PointFeature] = field(default_factory=list)

