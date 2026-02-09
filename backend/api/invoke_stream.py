from __future__ import annotations

import json
import os
import time
from asyncio import sleep
from enum import Enum
from functools import lru_cache

from agent.router import route_prompt
from engine.duckdb import DuckDBEngine
from engine.in_memory import InMemoryEngine
from engine.types import LayerEngine, MapContext
from geo.aoi import BBox
from geo.tiles import tile_zoom_for_view_zoom, tiles_for_bbox
from lod.policy import apply_lod
from plotly.build_map import build_map_plot
from scenarios.registry import default_scenario_id, get_scenario
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
        highlight_layer_id or "",
        tuple(sorted(highlight_feature_ids or ())),
    )
    key = (
        scenario_id,
        engine_name,
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
        )

        engine_name = (
            _default_engine_name()
            if thread.engine is None
            else _normalize_engine(thread.engine)
        )
        if (scenario.dataSize or "small").lower() == "large":
            engine_name = "duckdb"
        t0 = time.perf_counter()
        result = _engine(engine_name).get(ctx)
        t_engine_get_ms = (time.perf_counter() - t0) * 1000.0
        aoi_layers = result.layers
        index = result.index

        t1 = time.perf_counter()
        response = route_prompt(
            prompt,
            layers=aoi_layers,
            index=index,
            aoi=aoi,
            view_center=ctx.view_center,
            routing=scenario.routing,
        )
        t_route_ms = (time.perf_counter() - t1) * 1000.0

        # Stream a short explanation.
        for word in response.message.replace("\n", " \n ").split():
            yield format_event(EventType.append, word)
            await sleep(0.02)

        t2 = time.perf_counter()
        (lod_layers, beer_clusters), cache_stats = _apply_lod_cached(
            engine_name=engine_name,
            layers=aoi_layers,
            aoi=aoi,
            view_zoom=thread.map.view.zoom,
            scenario_id=ctx.scenario_id,
            cluster_points_layer_id=scenario.plot.highlightLayerId,
            highlight_layer_id=response.highlight.layer_id
            if response.highlight is not None
            else None,
            highlight_feature_ids=response.highlight.feature_ids
            if response.highlight is not None
            else None,
        )
        t_lod_ms = (time.perf_counter() - t2) * 1000.0

        # Send the map payload before commit so frontend attaches it to the message.
        t3 = time.perf_counter()
        plot = build_map_plot(
            lod_layers,
            highlight=response.highlight,
            highlight_source_layers=aoi_layers,
            aoi=aoi,
            view_center=ctx.view_center,
            view_zoom=ctx.view_zoom,
            viewport=ctx.viewport,
            focus_map=response.focus_map,
            clusters=beer_clusters,
            cluster_layer_id=scenario.plot.highlightLayerId,
        )
        t_plot_ms = (time.perf_counter() - t3) * 1000.0
        try:
            plot["layout"]["meta"]["stats"]["cache"] = cache_stats
            plot["layout"]["meta"]["stats"]["engine"] = engine_name
            plot["layout"]["meta"]["stats"]["scenarioId"] = ctx.scenario_id
            plot["layout"]["meta"]["stats"]["scenarioDataSize"] = scenario.dataSize
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

        # If highlights were requested but clipped by budgets/policy, make it explicit.
        try:
            stats = (plot.get("layout", {}).get("meta", {}) or {}).get(
                "stats", {}
            ) or {}
            req = int(stats.get("highlightRequested") or 0)
            rend = int(stats.get("highlightRendered") or 0)
            if req and rend < req:
                note = f"(Note: matched {req}, rendered {rend} due to LOD/budget/caps.)"
                for word in note.split():
                    yield format_event(EventType.append, word)
        except Exception:
            pass

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
