from __future__ import annotations

import json
import time
from enum import Enum

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.invoke_stream import (
    _apply_lod_cached,
    _default_engine_name,
    _engine,
    _normalize_engine,
    handle_incoming_message,
)
from engine.duckdb_impl.geoparquet.pins import query_geoparquet_layer_pinned_ids
from engine.types import LayerBundle, MapContext
from geo.aoi import BBox
from layers.types import Layer
from plotly.build_map import build_map_plot
from scenarios.registry import (
    clear_registry_cache,
    default_scenario_id,
    get_scenario,
    list_scenarios,
    resolve_repo_path,
)
from telemetry.singleton import get_store, reset_store

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
    highlights: list[dict] | None = None
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

    scenario_id = body.scenarioId or default_scenario_id()
    scenario = get_scenario(scenario_id).config
    ctx = MapContext(
        scenario_id=scenario.id,
        aoi=aoi,
        view_center={"lat": body.map.view.center.lat, "lon": body.map.view.center.lon},
        view_zoom=body.map.view.zoom,
        viewport=(
            {
                "width": int(body.map.viewport.width),
                "height": int(body.map.viewport.height),
            }
            if body.map.viewport is not None
            else None
        ),
    )

    engine_name = (
        _default_engine_name()
        if body.engine is None
        else _normalize_engine(body.engine)
    )
    if (scenario.dataSize or "small").lower() == "large":
        engine_name = "duckdb"
    t0 = time.perf_counter()
    result = _engine(engine_name).get(ctx)
    t_engine_get_ms = (time.perf_counter() - t0) * 1000.0
    aoi_layers = result.layers

    payload_highlights = list(body.highlights or [])
    if body.highlight:
        payload_highlights = [body.highlight, *payload_highlights]
    highlight_ids_by_layer: dict[str, set[str]] = {}
    for raw in payload_highlights:
        lid = raw.get("layerId") if isinstance(raw, dict) else None
        ids = (
            (raw.get("featureIds") or raw.get("pointIds"))
            if isinstance(raw, dict)
            else None
        )
        if isinstance(lid, str) and lid and isinstance(ids, list):
            highlight_ids_by_layer.setdefault(lid, set()).update(
                set(str(x) for x in ids if isinstance(x, str))
            )

    # Pin highlighted features into the layer bundle so they don't disappear across zoom changes
    # when base layer queries are capped. (Best-effort; only for DuckDB+GeoParquet layers.)
    if engine_name == "duckdb" and highlight_ids_by_layer:
        try:
            import duckdb as _duckdb  # local import to keep startup light

            base_layers = list(aoi_layers.layers)
            conn = _duckdb.connect(database=":memory:", read_only=False)
            try:
                for hl_layer_id, ids in highlight_ids_by_layer.items():
                    layer_cfg = next(
                        (cfg for cfg in scenario.layers if cfg.id == hl_layer_id), None
                    )
                    if (
                        layer_cfg is None
                        or layer_cfg.source.type != "geoparquet"
                        or not isinstance(layer_cfg.source.geoparquet, dict)
                    ):
                        continue
                    pinned = query_geoparquet_layer_pinned_ids(
                        conn,
                        layer_id=layer_cfg.id,
                        kind=layer_cfg.kind,
                        title=layer_cfg.title,
                        style=layer_cfg.style or {},
                        path=resolve_repo_path(layer_cfg.source.path),
                        aoi=aoi,
                        view_zoom=ctx.view_zoom,
                        source_options=layer_cfg.source.geoparquet or None,
                        ids=ids,
                    )
                    for i, layer in enumerate(base_layers):
                        if layer.id != layer_cfg.id:
                            continue
                        merged = {getattr(f, "id", ""): f for f in layer.features}
                        for f in pinned.features:
                            fid = getattr(f, "id", "")
                            if fid:
                                merged[fid] = f
                        base_layers[i] = Layer(
                            id=layer.id,
                            kind=layer.kind,
                            title=layer.title,
                            features=[merged[k] for k in sorted(merged.keys()) if k],
                            style=layer.style,
                        )
                        break
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            aoi_layers = LayerBundle(layers=base_layers)
        except Exception:
            pass

    t1 = time.perf_counter()
    (lod_layers, beer_clusters), cache_stats = _apply_lod_cached(
        engine_name=engine_name,
        layers=aoi_layers,
        aoi=aoi,
        view_zoom=ctx.view_zoom,
        scenario_id=ctx.scenario_id,
        cluster_points_layer_id=scenario.plot.highlightLayerId,
        highlight_layer_id=next(iter(highlight_ids_by_layer.keys()), None),
        highlight_feature_ids=next(iter(highlight_ids_by_layer.values()), None),
        highlight_feature_ids_by_layer=highlight_ids_by_layer or None,
    )
    t_lod_ms = (time.perf_counter() - t1) * 1000.0

    highlight = None
    highlights = []
    for raw in payload_highlights:
        ids_raw = (
            raw.get("featureIds") or raw.get("pointIds")
            if isinstance(raw, dict)
            else None
        )
        if not (isinstance(raw, dict) and isinstance(ids_raw, list) and ids_raw):
            continue
        from plotly.build_map import Highlight as PlotHighlight

        hl_layer_id = str(raw.get("layerId") or scenario.plot.highlightLayerId)
        hl_ids = set(str(x) for x in ids_raw if isinstance(x, str))
        highlights.append(
            PlotHighlight(
                layer_id=hl_layer_id,
                feature_ids=hl_ids,
                title=raw.get("title") or "Highlighted",
                mode=str(raw.get("mode") or "toggle"),
            )
        )
    if highlights:
        highlight = highlights[0]

    t2 = time.perf_counter()
    payload = build_map_plot(
        lod_layers,
        highlight=highlight,
        highlights=highlights or None,
        highlight_source_layers=aoi_layers,
        aoi=aoi,
        view_center=ctx.view_center,
        view_zoom=ctx.view_zoom,
        viewport=ctx.viewport,
        focus_map=False,
        clusters=beer_clusters,
        cluster_layer_id=scenario.plot.highlightLayerId,
    )
    t_plot_ms = (time.perf_counter() - t2) * 1000.0

    t_json0 = time.perf_counter()
    payload_json = json.dumps(payload, ensure_ascii=False)
    t_json_ms = (time.perf_counter() - t_json0) * 1000.0
    payload_bytes = len(payload_json)
    try:
        payload["layout"]["meta"]["stats"]["cache"] = cache_stats
        payload["layout"]["meta"]["stats"]["engine"] = engine_name
        payload["layout"]["meta"]["stats"]["scenarioId"] = ctx.scenario_id
        payload["layout"]["meta"]["stats"]["scenarioDataSize"] = scenario.dataSize
        payload["layout"]["meta"]["stats"]["payloadBytes"] = payload_bytes
        if getattr(result, "stats", None):
            payload["layout"]["meta"]["stats"]["engineStats"] = result.stats
        payload["layout"]["meta"]["stats"]["timingsMs"] = {
            "engineGet": round(t_engine_get_ms, 2),
            "lod": round(t_lod_ms, 2),
            "plot": round(t_plot_ms, 2),
            "jsonSerialize": round(t_json_ms, 2),
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
                stats=(payload.get("layout", {}).get("meta", {}) or {}).get(
                    "stats", {}
                ),
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
        has_geoparquet = any(
            (layer_cfg.source.type == "geoparquet") for layer_cfg in (s.layers or [])
        )
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


@app.post("/dev/clear-caches")
def dev_clear_caches():
    """
    Dev helper: clear in-memory caches (scenario registry, LOD cache, engine singletons).

    Some caches intentionally trade correctness for speed and are not hot-reload aware.
    This avoids requiring a backend restart after editing scenario YAML.
    """
    clear_registry_cache()
    cache_stats = {}
    try:
        # Clears LOD cache + engine singleton caches (DuckDB/InMemory engine objects).
        from api.invoke_stream import clear_in_memory_caches

        cache_stats = clear_in_memory_caches()
    except Exception:
        cache_stats = {}
    return {"ok": True, **cache_stats}


@app.get("/telemetry/summary")
def telemetry_summary(
    engine: str | None = None, endpoint: str | None = None, since_ms: int | None = None
):
    store = get_store()
    if store is None:
        return {"enabled": False, "rows": []}
    # Best-effort: include recent writes.
    try:
        store.flush(timeout_s=0.5)
    except Exception:
        pass
    return {
        "enabled": True,
        "rows": store.summary(engine=engine, endpoint=endpoint, since_ms=since_ms),
    }


@app.get("/telemetry/slowest")
def telemetry_slowest(
    engine: str | None = None, endpoint: str | None = None, limit: int = 25
):
    store = get_store()
    if store is None:
        return {"enabled": False, "rows": []}
    try:
        store.flush(timeout_s=0.5)
    except Exception:
        pass
    return {
        "enabled": True,
        "rows": store.slowest(engine=engine, endpoint=endpoint, limit=limit),
    }
