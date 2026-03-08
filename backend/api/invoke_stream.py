from __future__ import annotations

import json
import os
import time
from asyncio import sleep
from enum import Enum
from functools import lru_cache

from agent.router import route_prompt
from engine.duckdb import DuckDBEngine
from engine.duckdb_impl.geoparquet.cluster_counts import (
    enrich_clusters_with_exact_counts,
    query_exact_density_bins,
)
from engine.in_memory import InMemoryEngine
from engine.types import LayerEngine, MapContext
from flood.selection import filter_flood_layer_for_request, parse_request_flood_context
from geo.aoi import BBox
from geo.tiles import tile_zoom_for_view_zoom, tiles_for_bbox
from lod.policy import apply_lod
from lod.points import density_grid_size_m, grid_size_m
from map_context import parse_request_inspect_mode
from place.selection import (
    filter_points_layer_by_category,
    parse_request_place_categories,
)
from plotly.build_map import build_map_plot
from scenarios.registry import default_scenario_id, get_scenario, resolve_repo_path
from telemetry.singleton import get_store


class EventType(str, Enum):
    append = "append"
    commit = "commit"
    plot_data = "plot_data"


def format_event(type: EventType, data: str):
    return f"event: {type.value}\ndata: {data}\n\n"


@lru_cache(maxsize=1)
def _default_engine_name() -> str:
    return _normalize_engine(os.getenv("PANGE_ENGINE"))


def _normalize_engine(name: str | None) -> str:
    n = (name or "in_memory").strip().lower()
    if n in {"duckdb", "in_memory"}:
        return n
    return "in_memory"


def _resolve_engine_name_for_scenario(*, scenario, requested_engine: str | None) -> str:
    """
    Resolve effective engine using YAML policy + layer source auto-detection.
    """
    runtime_policy = (
        getattr(getattr(scenario, "runtime", None), "enginePolicy", "auto") or "auto"
    )
    if runtime_policy in {"duckdb", "in_memory"}:
        return runtime_policy

    # Auto policy: if any layer uses GeoParquet, force DuckDB.
    has_geoparquet_layers = any(
        layer_cfg.source.type == "geoparquet" for layer_cfg in (scenario.layers or [])
    )
    if has_geoparquet_layers:
        return "duckdb"

    return (
        _default_engine_name()
        if requested_engine is None
        else _normalize_engine(requested_engine)
    )


@lru_cache(maxsize=2)
def _engine(name: str) -> LayerEngine:
    if name == "duckdb":
        return DuckDBEngine()
    return InMemoryEngine()


_lod_cache: dict[tuple, tuple] = {}


def _bounded_cache_put(cache: dict, key, value, *, max_items: int) -> None:
    cache[key] = value
    if len(cache) > max_items:
        try:
            oldest = next(iter(cache.keys()))
            if oldest != key:
                cache.pop(oldest, None)
        except Exception:
            pass


def _apply_lod_cached(
    *,
    engine_name: str,
    layers,
    aoi: BBox,
    view_zoom: float,
    scenario_id: str,
    cluster_points_layer_id: str,
    highlight_layer_id: str | None,
    highlight_feature_ids: set[str] | None,
    highlight_feature_ids_by_layer: dict[str, set[str]] | None = None,
    cache_scope: tuple | None = None,
):
    """
    Cache LOD output by AOI bucket + zoom bucket.

    This is primarily used by `/plot` refreshes on pan/zoom and should make them cheap.
    """
    tile_zoom = tile_zoom_for_view_zoom(view_zoom)
    tiles = tuple(sorted(tiles_for_bbox(tile_zoom, aoi), key=lambda t: (t[1], t[2])))
    aoi_key = aoi.rounded_key(decimals=4)
    zoom_bucket = int(round(float(view_zoom) * 2.0))  # 0.5 zoom buckets
    highlight_key = (
        tuple(
            sorted(
                (
                    (lid, tuple(sorted(ids)))
                    for lid, ids in (highlight_feature_ids_by_layer or {}).items()
                    if lid and ids
                ),
                key=lambda row: row[0],
            )
        ),
        highlight_layer_id or "",
        tuple(sorted(highlight_feature_ids or ())),
    )
    key = (
        scenario_id,
        engine_name,
        cache_scope or (),
        cluster_points_layer_id,
        tile_zoom,
        zoom_bucket,
        tiles,
        aoi_key,
        highlight_key,
    )

    cached = _lod_cache.get(key)
    if cached is not None:
        return cached, {
            "tileZoom": tile_zoom,
            "tilesUsed": len(tiles),
            "zoomBucket": zoom_bucket / 2.0,
            "aoiKey": aoi_key,
            "cacheHit": True,
        }

    lod_layers, beer_clusters = apply_lod(
        layers,
        view_zoom=view_zoom,
        highlight_layer_id=highlight_layer_id,
        highlight_feature_ids=highlight_feature_ids,
        highlight_feature_ids_by_layer=highlight_feature_ids_by_layer,
        cluster_points_layer_id=cluster_points_layer_id,
    )
    value = (lod_layers, beer_clusters)
    _bounded_cache_put(_lod_cache, key, value, max_items=64)
    return value, {
        "tileZoom": tile_zoom,
        "tilesUsed": len(tiles),
        "zoomBucket": zoom_bucket / 2.0,
        "aoiKey": aoi_key,
        "cacheHit": False,
    }


def _gp_layer_stats(engine_stats: dict | None, layer_id: str) -> dict[str, object] | None:
    if not isinstance(engine_stats, dict):
        return None
    gp = engine_stats.get("geoparquet")
    if not isinstance(gp, dict):
        return None
    rows = gp.get("layers")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("layerId") or "") == layer_id:
            return row
    return None


def _flooded_count_approximation(
    engine_stats: dict | None, *, points_layer_id: str, mask_layer_id: str | None
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for lid in [points_layer_id, mask_layer_id]:
        if not lid:
            continue
        row = _gp_layer_stats(engine_stats, lid)
        if row is None:
            continue
        skipped_reason = str(row.get("skippedReason") or "").strip()
        if skipped_reason:
            reasons.append(f"{lid}:{skipped_reason}")
            continue
        cap = row.get("cap")
        if isinstance(cap, dict):
            effective = cap.get("effectiveLimit")
            n = row.get("n")
            if isinstance(effective, (int, float)) and isinstance(n, (int, float)):
                if float(effective) > 0 and float(n) >= float(effective):
                    reasons.append(f"{lid}:capped@{int(effective)}")
    return bool(reasons), reasons


def clear_in_memory_caches() -> dict[str, int]:
    """
    Clear in-process caches that can block hot reload of config changes.

    This endpoint is intended for development only.
    """
    lod_before = len(_lod_cache)
    _lod_cache.clear()
    try:
        _engine.cache_clear()
    except Exception:
        pass
    try:
        _default_engine_name.cache_clear()
    except Exception:
        pass
    return {
        "lodCacheBefore": int(lod_before),
        "lodCacheAfter": int(len(_lod_cache)),
    }


async def handle_incoming_message(thread):
    prompt = thread.messages[-1].text if thread.messages else ""

    try:
        bbox = thread.map.bbox
        aoi = BBox(
            min_lon=bbox.minLon,
            min_lat=bbox.minLat,
            max_lon=bbox.maxLon,
            max_lat=bbox.maxLat,
        ).normalized()

        scenario_id = thread.scenarioId or default_scenario_id()
        scenario = get_scenario(scenario_id).config
        ctx = MapContext(
            scenario_id=scenario.id,
            aoi=aoi,
            view_center={
                "lat": thread.map.view.center.lat,
                "lon": thread.map.view.center.lon,
            },
            view_zoom=thread.map.view.zoom,
            viewport=(
                {
                    "width": int(thread.map.viewport.width),
                    "height": int(thread.map.viewport.height),
                }
                if thread.map.viewport is not None
                else None
            ),
            request_context=(
                thread.map.context.model_dump(exclude_none=True)
                if getattr(thread.map, "context", None) is not None
                else None
            ),
        )

        engine_name = _resolve_engine_name_for_scenario(
            scenario=scenario, requested_engine=thread.engine
        )
        t0 = time.perf_counter()
        result = _engine(engine_name).get(ctx)
        t_engine_get_ms = (time.perf_counter() - t0) * 1000.0
        aoi_layers = result.layers
        index = result.index
        flood_risk_level, selected_zone_ids = parse_request_flood_context(
            ctx.request_context
        )
        place_categories = parse_request_place_categories(ctx.request_context)
        inspect_mode = parse_request_inspect_mode(ctx.request_context)
        place_filter_stats: dict[str, object] | None = None
        if scenario.routing.primaryPointsLayerId:
            aoi_layers, place_filter_stats = filter_points_layer_by_category(
                aoi_layers,
                layer_id=scenario.routing.primaryPointsLayerId,
                selected_categories=place_categories,
            )
        flood_filter_stats: dict[str, object] | None = None
        if scenario.routing.maskPolygonsLayerId:
            aoi_layers, flood_filter_stats, _active_flood_zones = (
                filter_flood_layer_for_request(
                    aoi_layers,
                    layer_id=scenario.routing.maskPolygonsLayerId,
                    flood_risk_level=flood_risk_level,
                    selected_zone_ids=selected_zone_ids,
                )
            )

        t1 = time.perf_counter()
        response = route_prompt(
            prompt,
            layers=aoi_layers,
            index=index,
            aoi=aoi,
            view_center=ctx.view_center,
            routing=scenario.routing,
            request_context=ctx.request_context,
        )
        t_route_ms = (time.perf_counter() - t1) * 1000.0
        count_stats = (
            dict(response.count_stats)
            if isinstance(response.count_stats, dict)
            else None
        )
        if (
            count_stats is not None
            and str(count_stats.get("promptType") or "") == "flooded_count"
        ):
            approximate, reasons = _flooded_count_approximation(
                result.stats if isinstance(result.stats, dict) else None,
                points_layer_id=scenario.routing.primaryPointsLayerId,
                mask_layer_id=scenario.routing.maskPolygonsLayerId,
            )
            count_stats["approximate"] = approximate
            count_stats["approximationReason"] = ", ".join(reasons) if reasons else None

        active_highlights = (
            list(response.highlights or [])
            if response.highlights is not None
            else ([response.highlight] if response.highlight is not None else [])
        )
        highlight_ids_by_layer: dict[str, set[str]] = {}
        for h in active_highlights:
            if not h.feature_ids:
                continue
            highlight_ids_by_layer.setdefault(h.layer_id, set()).update(h.feature_ids)
        primary_highlight = active_highlights[0] if active_highlights else None

        t2 = time.perf_counter()
        (lod_layers, beer_clusters), cache_stats = _apply_lod_cached(
            engine_name=engine_name,
            layers=aoi_layers,
            aoi=aoi,
            view_zoom=thread.map.view.zoom,
            scenario_id=ctx.scenario_id,
            cluster_points_layer_id=scenario.plot.highlightLayerId,
            cache_scope=(
                tuple(sorted(place_categories or set())),
                flood_risk_level,
                tuple(sorted(selected_zone_ids)),
            ),
            highlight_layer_id=primary_highlight.layer_id
            if primary_highlight is not None
            else None,
            highlight_feature_ids=primary_highlight.feature_ids
            if primary_highlight is not None
            else None,
            highlight_feature_ids_by_layer=highlight_ids_by_layer or None,
        )
        t_lod_ms = (time.perf_counter() - t2) * 1000.0
        if (
            engine_name == "duckdb"
            and beer_clusters is not None
            and scenario.plot.highlightLayerId
        ):
            try:
                points_cfg = next(
                    (
                        layer_cfg
                        for layer_cfg in scenario.layers
                        if layer_cfg.id == scenario.plot.highlightLayerId
                        and layer_cfg.kind == "points"
                    ),
                    None,
                )
                if points_cfg is not None and points_cfg.source.type == "geoparquet":
                    density_grid_m = density_grid_size_m(ctx.view_zoom)
                    beer_clusters = query_exact_density_bins(
                        path=resolve_repo_path(points_cfg.source.path),
                        aoi=aoi,
                        grid_m=density_grid_m,
                        place_category_filter=place_categories,
                    )
            except Exception:
                try:
                    beer_clusters = enrich_clusters_with_exact_counts(
                        path=resolve_repo_path(points_cfg.source.path),
                        aoi=aoi,
                        clusters=beer_clusters,
                        grid_m=grid_size_m(ctx.view_zoom),
                        place_category_filter=place_categories,
                    )
                except Exception:
                    pass

        # Send the map payload before commit so frontend attaches it to the message.
        t3 = time.perf_counter()
        plot = build_map_plot(
            lod_layers,
            highlight=primary_highlight,
            highlights=active_highlights or None,
            highlight_source_layers=aoi_layers,
            aoi=aoi,
            view_center=ctx.view_center,
            view_zoom=ctx.view_zoom,
            viewport=ctx.viewport,
            focus_map=response.focus_map,
            clusters=beer_clusters,
            cluster_layer_id=scenario.plot.highlightLayerId,
            inspect_mode=inspect_mode,
        )
        t_plot_ms = (time.perf_counter() - t3) * 1000.0
        try:
            plot["layout"]["meta"]["stats"]["cache"] = cache_stats
            plot["layout"]["meta"]["stats"]["engine"] = engine_name
            plot["layout"]["meta"]["stats"]["scenarioId"] = ctx.scenario_id
            plot["layout"]["meta"]["stats"]["scenarioDataSize"] = scenario.dataSize
            plot["layout"]["meta"]["stats"]["placeControl"] = place_filter_stats
            plot["layout"]["meta"]["stats"]["floodSelection"] = flood_filter_stats
            plot["layout"]["meta"]["stats"]["inspectMode"] = inspect_mode
            if count_stats is not None:
                plot["layout"]["meta"]["stats"]["promptType"] = "flooded_count"
                plot["layout"]["meta"]["stats"]["countStats"] = count_stats
            if getattr(result, "stats", None):
                plot["layout"]["meta"]["stats"]["engineStats"] = result.stats
            t_json0 = time.perf_counter()
            plot_json = json.dumps(plot, ensure_ascii=False)
            t_json_ms = (time.perf_counter() - t_json0) * 1000.0
            plot["layout"]["meta"]["stats"]["payloadBytes"] = len(plot_json)
            plot["layout"]["meta"]["stats"]["timingsMs"] = {
                "engineGet": round(t_engine_get_ms, 2),
                "route": round(t_route_ms, 2),
                "lod": round(t_lod_ms, 2),
                "plot": round(t_plot_ms, 2),
                "jsonSerialize": round(t_json_ms, 2),
                "total": round((time.perf_counter() - t0) * 1000.0, 2),
            }
        except Exception:
            plot_json = json.dumps(plot)

        stream_message = response.message
        # If highlights were requested but clipped by budgets/policy, make it explicit.
        try:
            stats = (plot.get("layout", {}).get("meta", {}) or {}).get(
                "stats", {}
            ) or {}
            req = int(stats.get("highlightRequested") or 0)
            rend = int(stats.get("highlightRendered") or 0)
            if req and rend < req:
                clipped_note = f"Highlights: matched {req}, rendering {rend} due to budget."
                stream_message = (
                    f"{stream_message}\n{clipped_note}" if stream_message else clipped_note
                )
        except Exception:
            pass

        # Stream a short explanation after we know final highlight stats.
        for word in stream_message.replace("\n", " \n ").split():
            yield format_event(EventType.append, word)
            await sleep(0.02)

        # Persist telemetry for later analysis (best-effort).
        try:
            store = get_store()
            if store is not None:
                store.record(
                    endpoint="/invoke",
                    prompt=prompt,
                    engine=engine_name,
                    view_zoom=ctx.view_zoom,
                    aoi={
                        "minLon": aoi.min_lon,
                        "minLat": aoi.min_lat,
                        "maxLon": aoi.max_lon,
                        "maxLat": aoi.max_lat,
                    },
                    stats=(plot.get("layout", {}).get("meta", {}) or {}).get(
                        "stats", {}
                    ),
                )
        except Exception:
            pass
        yield format_event(EventType.plot_data, plot_json)

        # Commit the message (punctuation ends the buffer on frontend).
        yield format_event(EventType.commit, ".")
    except Exception as e:
        msg = f"Backend error: {type(e).__name__}: {e}"
        for word in msg.split():
            yield format_event(EventType.append, word)
        yield format_event(EventType.commit, ".")
