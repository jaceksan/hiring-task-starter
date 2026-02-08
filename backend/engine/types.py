from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from geo.aoi import BBox
from geo.ops import GeoIndex
from layers.types import PragueLayers


@dataclass(frozen=True)
class MapContext:
    """
    Request-scoped map context coming from the frontend.
    """

    aoi: BBox
    view_center: dict[str, float]  # {"lat": ..., "lon": ...}
    view_zoom: float


@dataclass(frozen=True)
class EngineResult:
    """
    What an engine returns for a given request.
    """

    layers: PragueLayers
    index: GeoIndex


class LayerEngine(Protocol):
    """
    Data engine interface.

    - InMemoryEngine: slices preloaded layers via STRtree
    - DuckDBEngine: (later) queries GeoParquet by AOI
    """

    def get(self, ctx: MapContext) -> EngineResult: ...

