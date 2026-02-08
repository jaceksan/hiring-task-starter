from __future__ import annotations

from functools import lru_cache

from engine.types import EngineResult, LayerEngine, MapContext
from geo.ops import build_geo_index
from geo.tiles import tile_zoom_for_view_zoom
from layers.load_prague import load_prague_layers


class InMemoryEngine(LayerEngine):
    """
    Loads Prague layers into memory once, builds an STRtree-backed index,
    then slices by AOI for each request.
    """

    @staticmethod
    @lru_cache(maxsize=1)
    def _base():
        layers = load_prague_layers()
        index = build_geo_index(layers)
        return layers, index

    def get(self, ctx: MapContext) -> EngineResult:
        _layers, index = self._base()
        tile_zoom = tile_zoom_for_view_zoom(ctx.view_zoom)
        aoi_layers = index.slice_layers_tiled(ctx.aoi, tile_zoom=tile_zoom)
        return EngineResult(layers=aoi_layers, index=index)

