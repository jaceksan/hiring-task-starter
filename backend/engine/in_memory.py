from __future__ import annotations

from functools import lru_cache

from engine.types import EngineResult, LayerEngine, MapContext
from geo.ops import build_geo_index
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
        aoi_layers = index.slice_layers(ctx.aoi)
        return EngineResult(layers=aoi_layers, index=index)

