from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb
from shapely.wkb import loads as wkb_loads

from engine.duckdb_common import bounded_cache_put, duckdb_threads
from engine.duckdb_geoparquet import query_geoparquet_layers_cached
from engine.duckdb_seeded_db import (
    connect,
    init_schema,
    query_seeded_layers_bbox,
    seed_all_layers,
)
from engine.types import EngineResult, LayerEngine, MapContext
from geo.aoi import BBox
from geo.index import GeoIndex, build_geo_index
from geo.tiles import tile_bbox_4326, tile_zoom_for_view_zoom, tiles_for_bbox
from layers.load_scenario import load_scenario_layers
from layers.types import Layer, LayerBundle, LineFeature, PointFeature, PolygonFeature
from scenarios.registry import default_scenario_id, get_scenario, resolve_repo_path


class DuckDBEngine(LayerEngine):
    """
    DuckDB-backed engine.

    Two modes:
    - Seeded mode (small scenarios): load features into generic DuckDB tables once.
    - Query-on-read GeoParquet mode (large scenarios): read parquet per AOI directly.
    """

    def __init__(self, *, path: str | None = None):
        self.path = path or (os.getenv("PANGE_DUCKDB_PATH") or None)

    def get(self, ctx: MapContext) -> EngineResult:
        scenario = get_scenario(ctx.scenario_id).config
        has_geoparquet = any(l.source.type == "geoparquet" for l in scenario.layers)
        if has_geoparquet:
            layers = query_geoparquet_layers_cached(
                scenario.id,
                aoi=ctx.aoi,
                view_zoom=ctx.view_zoom,
            )
            index = build_geo_index(layers)
            return EngineResult(layers=layers, index=index)

        base = _seeded_base(
            _duckdb_path_for_scenario(ctx.scenario_id, override_path=self.path),
            ctx.scenario_id,
        )
        base.ensure_initialized()
        tile_zoom = tile_zoom_for_view_zoom(ctx.view_zoom)
        sliced = base.slice_layers_tiled(ctx.aoi, tile_zoom=tile_zoom)
        return EngineResult(layers=sliced, index=base.index)


@dataclass
class _SeededBase:
    scenario_id: str
    path: str
    index: GeoIndex
    layers: LayerBundle
    threads: int
    _init_lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _initialized: bool = field(default=False, repr=False)
    _local: threading.local = field(default_factory=threading.local, repr=False)

    def ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            conn = connect(self.path, threads=self.threads)
            try:
                init_schema(conn)
                seed_all_layers(conn, self.layers)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            self._initialized = True

    def _conn(self) -> duckdb.DuckDBPyConnection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = connect(self.path, threads=self.threads)
            self._local.conn = c
        return c

    def _tile_cache(self) -> dict[tuple[int, int, int], LayerBundle]:
        cache = getattr(self._local, "tile_slice_cache", None)
        if cache is None:
            cache = {}
            self._local.tile_slice_cache = cache
        return cache

    def slice_layers_tiled(self, aoi: BBox, *, tile_zoom: int) -> LayerBundle:
        tiles = tiles_for_bbox(tile_zoom, aoi)
        if not tiles:
            return LayerBundle(
                layers=[
                    Layer(
                        id=l.id, kind=l.kind, title=l.title, features=[], style=l.style
                    )
                    for l in self.layers.layers
                ]
            )
        tiles = sorted(tiles, key=lambda t: (t[1], t[2]))

        conn = self._conn()
        cache = self._tile_cache()

        merged: dict[str, dict[str, Any]] = {l.id: {} for l in self.layers.layers}
        for z, x, y in tiles:
            key = (int(z), int(x), int(y))
            cached = cache.get(key)
            if cached is None:
                tb = tile_bbox_4326(z, x, y)
                cached = query_seeded_layers_bbox(
                    conn, tb, scenario_id=self.scenario_id
                )
                bounded_cache_put(cache, key, cached, max_items=256)
            for l in cached.layers:
                bucket = merged.get(l.id)
                if bucket is None:
                    bucket = {}
                    merged[l.id] = bucket
                for f in l.features:
                    bucket.setdefault(getattr(f, "id", ""), f)

        out_layers: list[Layer] = []
        for base in self.layers.layers:
            feats = merged.get(base.id, {})
            ordered = [feats[k] for k in sorted(feats.keys()) if k]
            out_layers.append(
                Layer(
                    id=base.id,
                    kind=base.kind,
                    title=base.title,
                    features=ordered,
                    style=base.style,
                )
            )
        return LayerBundle(layers=out_layers)


@lru_cache(maxsize=8)
def _seeded_base(path: str, scenario_id: str) -> _SeededBase:
    layers = load_scenario_layers(scenario_id)
    index = build_geo_index(layers)
    threads = duckdb_threads()
    return _SeededBase(
        scenario_id=scenario_id, path=path, index=index, layers=layers, threads=threads
    )


def _duckdb_path_for_scenario(
    scenario_id: str | None, *, override_path: str | None
) -> str:
    if override_path:
        return override_path
    env_path = (os.getenv("PANGE_DUCKDB_PATH") or "").strip()
    if env_path:
        return env_path
    sid = (scenario_id or "").strip() or default_scenario_id()
    base_dir = (os.getenv("PANGE_DUCKDB_DIR") or "data/duckdb").strip() or "data/duckdb"
    return str(Path(base_dir) / f"{sid}.duckdb")


#
# NOTE: GeoParquet querying moved to `engine/duckdb_geoparquet.py` and helpers to
# `engine/duckdb_common.py` to keep this file short.
