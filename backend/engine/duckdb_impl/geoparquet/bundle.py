from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import duckdb

from engine.duckdb_common import duckdb_threads
from engine.duckdb_impl.geoparquet.layer import query_geoparquet_layer_bbox
from geo.aoi import BBox
from layers.types import Layer, LayerBundle
from scenarios.registry import get_scenario, resolve_repo_path


def _geoparquet_cache_decimals() -> int:
    raw = (os.getenv("PANGE_GEOPARQUET_AOI_DECIMALS") or "").strip()
    if raw:
        try:
            return max(2, min(6, int(raw)))
        except Exception:
            pass
    return 3


@lru_cache(maxsize=128)
def _geoparquet_bundle_cached(
    scenario_id: str,
    *,
    aoi_key: tuple[float, float, float, float],
    zoom_bucket: int,
) -> tuple[LayerBundle, dict[str, Any]]:
    scenario = get_scenario(scenario_id).config
    aoi = BBox(
        min_lon=aoi_key[0], min_lat=aoi_key[1], max_lon=aoi_key[2], max_lat=aoi_key[3]
    )
    view_zoom = float(zoom_bucket) / 2.0

    conn = duckdb.connect(
        database=":memory:", read_only=False, config={"threads": int(duckdb_threads())}
    )
    try:
        out_layers: list[Layer] = []
        layer_stats: list[dict[str, Any]] = []
        for layer_cfg in scenario.layers:
            if layer_cfg.source.type != "geoparquet":
                out_layers.append(
                    Layer(
                        id=layer_cfg.id,
                        kind=layer_cfg.kind,
                        title=layer_cfg.title,
                        features=[],
                        style=layer_cfg.style or {},
                    )
                )
                layer_stats.append(
                    {
                        "layerId": layer_cfg.id,
                        "kind": layer_cfg.kind,
                        "source": layer_cfg.source.type,
                        "n": 0,
                    }
                )
                continue
            p = resolve_repo_path(layer_cfg.source.path)
            layer, stats = query_geoparquet_layer_bbox(
                conn,
                layer_id=layer_cfg.id,
                kind=layer_cfg.kind,
                title=layer_cfg.title,
                style=layer_cfg.style or {},
                path=p,
                aoi=aoi,
                view_zoom=view_zoom,
                source_options=layer_cfg.source.geoparquet or None,
            )
            out_layers.append(layer)
            layer_stats.append(stats)
        return LayerBundle(layers=out_layers), {
            "aoiKey": aoi_key,
            "zoomBucket": zoom_bucket,
            "layers": layer_stats,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


def query_geoparquet_layers_cached(
    scenario_id: str, *, aoi: BBox, view_zoom: float
) -> tuple[LayerBundle, dict[str, Any]]:
    decimals = _geoparquet_cache_decimals()
    aoi_key = aoi.rounded_key(decimals)
    zoom_bucket = int(round(float(view_zoom) * 2.0))
    return _geoparquet_bundle_cached(
        scenario_id, aoi_key=aoi_key, zoom_bucket=zoom_bucket
    )
