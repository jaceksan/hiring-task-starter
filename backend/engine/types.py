from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from geo.aoi import BBox
from geo.index import GeoIndex
from layers.types import LayerBundle


@dataclass(frozen=True)
class MapContext:
    """
    Request-scoped map context coming from the frontend.
    """

    scenario_id: str
    aoi: BBox
    view_center: dict[str, float]  # {"lat": ..., "lon": ...}
    view_zoom: float
    # Optional: real pixel size of the map viewport. Used for server-side "fit view" heuristics.
    viewport: dict[str, int] | None = None


@dataclass(frozen=True)
class EngineResult:
    """
    What an engine returns for a given request.
    """

    layers: LayerBundle
    index: GeoIndex


class LayerEngine(Protocol):
    """
    Data engine interface.

    - InMemoryEngine: slices preloaded layers via STRtree
    - DuckDBEngine: (later) queries GeoParquet by AOI
    """

    def get(self, ctx: MapContext) -> EngineResult: ...
