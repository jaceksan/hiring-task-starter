from __future__ import annotations

import json
import os
import time
from asyncio import sleep
from enum import Enum
from functools import lru_cache

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.router import route_prompt
from engine.duckdb import DuckDBEngine
from engine.in_memory import InMemoryEngine
from engine.types import LayerEngine, MapContext
from geo.aoi import BBox
from geo.tiles import tile_zoom_for_view_zoom, tiles_for_bbox
from lod.policy import apply_lod
from plotly.build_map import build_map_plot
from scenarios.registry import default_scenario_id, get_scenario, list_scenarios
from telemetry.store import get_store, reset_store

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ApiMessageSenderEnum(str, Enum):
    human = "human"
    ai = "ai"


class ApiMessage(BaseModel):
    id: int
    author: ApiMessageSenderEnum
    text: str


class ApiBbox(BaseModel):
    minLon: float
    minLat: float
    maxLon: float
    maxLat: float


class ApiCenter(BaseModel):
    lat: float
    lon: float


class ApiMapView(BaseModel):
    center: ApiCenter
    zoom: float


class ApiViewport(BaseModel):
    width: int
    height: int


class ApiMapContext(BaseModel):
    bbox: ApiBbox
    view: ApiMapView
    viewport: ApiViewport | None = None


class ApiThread(BaseModel):
    id: int
    title: str
    messages: list[ApiMessage]
    map: ApiMapContext
    engine: str | None = None
    scenarioId: str | None = None


class ApiPlotRequest(BaseModel):
    map: ApiMapContext
    highlight: dict | None = None
    engine: str | None = None
    scenarioId: str | None = None


@app.post("/invoke")
def invoke(body: ApiThread):
    return StreamingResponse(
        handle_incoming_message(body), media_type="text/event-stream"
    )


@app.post("/plot")
def plot(body: ApiPlotRequest):
    """
    Return a Plotly payload for the given map context.

    Used by the frontend to refresh LOD automatically on pan/zoom without creating chat messages.
    """
    bbox = body.map.bbox
    aoi = BBox(
        min_lon=bbox.minLon,
        min_lat=bbox.minLat,
        max_lon=bbox.maxLon,
        max_lat=bbox.maxLat,
    ).normalized()

    scenario_id = (body.scenarioId or default_scenario_id())
    scenario = get_scenario(scenario_id).config
    ctx = MapContext(
        scenario_id=scenario.id,
        aoi=aoi,
        view_center={"lat": body.map.view.center.lat, "lon": body.map.view.center.lon},
        view_zoom=body.map.view.zoom,
        viewport=(
            {"width": int(body.map.viewport.width), "height": int(body.map.viewport.height)}
            if body.map.viewport is not None
            else None
        ),
    )

    engine_name = _default_engine_name() if body.engine is None else _normalize_engine(body.engine)
    if (scenario.dataSize or "small").lower() == "large":
        engine_name = "duckdb"
    t0 = time.perf_counter()
    result = _engine(engine_name).get(ctx)
    t_engine_get_ms = (time.perf_counter() - t0) * 1000.0
    aoi_layers = result.layers

    t1 = time.perf_counter()
    (lod_layers, beer_clusters), cache_stats = _apply_lod_cached(
        engine_name=engine_name,
        layers=aoi_layers,
        aoi=aoi,
        view_zoom=ctx.view_zoom,
        scenario_id=ctx.scenario_id,
        cluster_points_layer_id=scenario.plot.highlightLayerId,
        highlight_layer_id=str(body.highlight.get("layerId") or scenario.plot.highlightLayerId)
        if body.highlight
        else None,
        highlight_feature_ids=(
            set(body.highlight.get("featureIds") or body.highlight.get("pointIds") or [])
            if body.highlight
            else None
        ),
    )
    t_lod_ms = (time.perf_counter() - t1) * 1000.0

    highlight = None
    if body.highlight and (body.highlight.get("featureIds") or body.highlight.get("pointIds")):
        from plotly.build_map import Highlight as PlotHighlight

        hl_layer_id = str(body.highlight.get("layerId") or scenario.plot.highlightLayerId)
        hl_ids = set(body.highlight.get("featureIds") or body.highlight.get("pointIds") or [])
        highlight = PlotHighlight(
            layer_id=hl_layer_id,
            feature_ids=hl_ids,
            title=body.highlight.get("title") or "Highlighted",
        )

    t2 = time.perf_counter()
    payload = build_map_plot(
        lod_layers,
        highlight=highlight,
        aoi=aoi,
        view_center=ctx.view_center,
        view_zoom=ctx.view_zoom,
        viewport=ctx.viewport,
        focus_map=False,
        clusters=beer_clusters,
        cluster_layer_id=scenario.plot.highlightLayerId,
    )
    t_plot_ms = (time.perf_counter() - t2) * 1000.0

    payload_bytes = len(json.dumps(payload, ensure_ascii=False))
    try:
        payload["layout"]["meta"]["stats"]["cache"] = cache_stats
        payload["layout"]["meta"]["stats"]["engine"] = engine_name
        payload["layout"]["meta"]["stats"]["scenarioId"] = ctx.scenario_id
        payload["layout"]["meta"]["stats"]["scenarioDataSize"] = scenario.dataSize
        payload["layout"]["meta"]["stats"]["payloadBytes"] = payload_bytes
        payload["layout"]["meta"]["stats"]["timingsMs"] = {
            "engineGet": round(t_engine_get_ms, 2),
            "lod": round(t_lod_ms, 2),
            "plot": round(t_plot_ms, 2),
            "total": round((time.perf_counter() - t0) * 1000.0, 2),
        }
    except Exception:
        pass

    # Persist telemetry for later analysis (best-effort).
    try:
        store = get_store()
        if store is not None:
            store.record(
                endpoint="/plot",
                prompt=None,
                engine=engine_name,
                view_zoom=ctx.view_zoom,
                aoi={
                    "minLon": aoi.min_lon,
                    "minLat": aoi.min_lat,
                    "maxLon": aoi.max_lon,
                    "maxLat": aoi.max_lat,
                },
                stats=(payload.get("layout", {}).get("meta", {}) or {}).get("stats", {}),
            )
    except Exception:
        pass
    return payload


@app.post("/telemetry/reset")
def telemetry_reset():
    reset_store()
    return {"ok": True}


@app.get("/scenarios")
def scenarios():
    """
    List available scenario packs discovered under `scenarios/*/scenario.yaml`.
    """
    out = []
    for s in list_scenarios():
        has_geoparquet = any((l.source.type == "geoparquet") for l in (s.layers or []))
        out.append(
            {
                "id": s.id,
                "title": s.title,
                "defaultView": s.defaultView.model_dump(),
                "dataSize": s.dataSize,
                "hasGeoParquet": bool(has_geoparquet),
                "enabled": bool(s.enabled),
                "examplePrompts": list(s.examplePrompts or []),
            }
        )
    return out


@app.get("/telemetry/summary")
def telemetry_summary(engine: str | None = None, endpoint: str | None = None, since_ms: int | None = None):
    store = get_store()
    if store is None:
        return {"enabled": False, "rows": []}
    # Best-effort: include recent writes.
    try:
        store.flush(timeout_s=0.5)
    except Exception:
        pass
    return {"enabled": True, "rows": store.summary(engine=engine, endpoint=endpoint, since_ms=since_ms)}


@app.get("/telemetry/slowest")
def telemetry_slowest(engine: str | None = None, endpoint: str | None = None, limit: int = 25):
    store = get_store()
    if store is None:
        return {"enabled": False, "rows": []}
    try:
        store.flush(timeout_s=0.5)
    except Exception:
        pass
    return {"enabled": True, "rows": store.slowest(engine=engine, endpoint=endpoint, limit=limit)}


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
    Cache LOD output by tile coverage and zoom bucket.

    This is primarily used by `/plot` refreshes on pan/zoom and should make them cheap.
    """
    tile_zoom = tile_zoom_for_view_zoom(view_zoom)
    tiles = tuple(sorted(tiles_for_bbox(tile_zoom, aoi), key=lambda t: (t[1], t[2])))
    zoom_bucket = int(round(float(view_zoom) * 2.0))  # 0.5 zoom buckets
    highlight_key = (highlight_layer_id or "", tuple(sorted(highlight_feature_ids or ())))
    key = (scenario_id, engine_name, cluster_points_layer_id, tile_zoom, zoom_bucket, tiles, highlight_key)

    cached = _lod_cache.get(key)
    if cached is not None:
        return cached, {
            "tileZoom": tile_zoom,
            "tilesUsed": len(tiles),
            "zoomBucket": zoom_bucket / 2.0,
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
        "cacheHit": False,
    }


async def handle_incoming_message(thread: ApiThread):
    prompt = thread.messages[-1].text if thread.messages else ""

    try:
        bbox = thread.map.bbox
        aoi = BBox(
            min_lon=bbox.minLon,
            min_lat=bbox.minLat,
            max_lon=bbox.maxLon,
            max_lat=bbox.maxLat,
        ).normalized()

        scenario_id = (thread.scenarioId or default_scenario_id())
        scenario = get_scenario(scenario_id).config
        ctx = MapContext(
            scenario_id=scenario.id,
            aoi=aoi,
            view_center={"lat": thread.map.view.center.lat, "lon": thread.map.view.center.lon},
            view_zoom=thread.map.view.zoom,
            viewport=(
                {"width": int(thread.map.viewport.width), "height": int(thread.map.viewport.height)}
                if thread.map.viewport is not None
                else None
            ),
        )

        engine_name = _default_engine_name() if thread.engine is None else _normalize_engine(thread.engine)
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
            highlight_layer_id=response.highlight.layer_id if response.highlight is not None else None,
            highlight_feature_ids=response.highlight.feature_ids if response.highlight is not None else None,
        )
        t_lod_ms = (time.perf_counter() - t2) * 1000.0

        # Send the map payload before commit so frontend attaches it to the message.
        t3 = time.perf_counter()
        plot = build_map_plot(
            lod_layers,
            highlight=response.highlight,
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
            plot_json = json.dumps(plot, ensure_ascii=False)
            plot["layout"]["meta"]["stats"]["payloadBytes"] = len(plot_json)
            plot["layout"]["meta"]["stats"]["timingsMs"] = {
                "engineGet": round(t_engine_get_ms, 2),
                "route": round(t_route_ms, 2),
                "lod": round(t_lod_ms, 2),
                "plot": round(t_plot_ms, 2),
                "total": round((time.perf_counter() - t0) * 1000.0, 2),
            }
        except Exception:
            plot_json = json.dumps(plot)

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
                    stats=(plot.get("layout", {}).get("meta", {}) or {}).get("stats", {}),
                )
        except Exception:
            pass
        yield format_event(EventType.plot_data, plot_json)

        # Commit the message (punctuation ends the buffer on frontend).
        yield format_event(EventType.commit, ".")
    except Exception as e:
        # Fail safe: return an error message but keep streaming protocol valid.
        msg = f"Backend error: {type(e).__name__}: {e}"
        for word in msg.split():
            yield format_event(EventType.append, word)
        yield format_event(EventType.commit, ".")
