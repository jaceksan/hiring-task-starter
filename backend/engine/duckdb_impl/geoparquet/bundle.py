from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
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

    # Option A: keep single /plot response, but query GeoParquet layers concurrently.
    # This avoids the complexity of partial Plotly merges on the frontend while reducing
    # perceived latency when one layer dominates.
    gp_layers = [lc for lc in scenario.layers if lc.source.type == "geoparquet"]
    max_workers = max(1, min(4, len(gp_layers)))
    total_threads = int(duckdb_threads())
    per_conn_threads = max(1, total_threads // max_workers) if total_threads > 0 else 1

    out_layers: list[Layer] = [
        Layer(
            id=layer_cfg.id,
            kind=layer_cfg.kind,
            title=layer_cfg.title,
            features=[],
            style=layer_cfg.style or {},
        )
        for layer_cfg in scenario.layers
    ]
    layer_stats: list[dict[str, Any]] = [
        {
            "layerId": layer_cfg.id,
            "kind": layer_cfg.kind,
            "source": layer_cfg.source.type,
            "n": 0,
        }
        for layer_cfg in scenario.layers
    ]

    def _query_one(i: int) -> tuple[int, Layer, dict[str, Any]]:
        layer_cfg = scenario.layers[i]
        p = resolve_repo_path(layer_cfg.source.path)
        conn = duckdb.connect(
            database=":memory:",
            read_only=False,
            config={"threads": int(per_conn_threads)},
        )
        try:
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
            return i, layer, stats
        finally:
            try:
                conn.close()
            except Exception:
                pass

    gp_indexes = [
        i for i, lc in enumerate(scenario.layers) if lc.source.type == "geoparquet"
    ]
    if gp_indexes:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_query_one, i): i for i in gp_indexes}
            for fut in as_completed(futures):
                i = futures[fut]
                try:
                    idx, layer, stats = fut.result()
                    out_layers[idx] = layer
                    layer_stats[idx] = stats
                except Exception:
                    # Best-effort: keep the layer empty and record a minimal error marker.
                    layer_stats[i] = {
                        "layerId": scenario.layers[i].id,
                        "kind": scenario.layers[i].kind,
                        "source": "geoparquet",
                        "n": 0,
                        "skippedReason": "error",
                    }

    return LayerBundle(layers=out_layers), {
        "aoiKey": aoi_key,
        "zoomBucket": zoom_bucket,
        "layers": layer_stats,
        "parallel": {
            "enabled": bool(gp_indexes),
            "workers": int(max_workers),
            "perConnThreads": int(per_conn_threads),
        },
    }


def query_geoparquet_layers_cached(
    scenario_id: str, *, aoi: BBox, view_zoom: float
) -> tuple[LayerBundle, dict[str, Any]]:
    decimals = _geoparquet_cache_decimals()
    aoi_key = aoi.rounded_key(decimals)
    zoom_bucket = int(round(float(view_zoom) * 2.0))
    return _geoparquet_bundle_cached(
        scenario_id, aoi_key=aoi_key, zoom_bucket=zoom_bucket
    )
