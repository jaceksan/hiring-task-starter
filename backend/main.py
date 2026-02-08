from __future__ import annotations

import json
import os
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
from plotly.build_plot import build_prague_plot

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


class ApiMapContext(BaseModel):
    bbox: ApiBbox
    view: ApiMapView


class ApiThread(BaseModel):
    id: int
    title: str
    messages: list[ApiMessage]
    map: ApiMapContext


class ApiPlotRequest(BaseModel):
    map: ApiMapContext
    highlight: dict | None = None


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

    ctx = MapContext(
        aoi=aoi,
        view_center={"lat": body.map.view.center.lat, "lon": body.map.view.center.lon},
        view_zoom=body.map.view.zoom,
    )

    result = _engine().get(ctx)
    aoi_layers = result.layers

    (lod_layers, beer_clusters), cache_stats = _apply_lod_cached(
        layers=aoi_layers,
        aoi=aoi,
        view_zoom=ctx.view_zoom,
        highlight_point_ids=set(body.highlight.get("pointIds") or []) if body.highlight else None,
    )

    highlight = None
    if body.highlight and body.highlight.get("pointIds"):
        from plotly.build_plot import Highlight as PlotHighlight

        highlight = PlotHighlight(
            point_ids=set(body.highlight.get("pointIds") or []),
            title=body.highlight.get("title") or "Highlighted",
        )

    payload = build_prague_plot(
        lod_layers,
        highlight=highlight,
        aoi=aoi,
        view_center=ctx.view_center,
        view_zoom=ctx.view_zoom,
        focus_map=False,
        beer_clusters=beer_clusters,
    )
    try:
        payload["layout"]["meta"]["stats"]["cache"] = cache_stats
    except Exception:
        pass
    return payload


class EventType(str, Enum):
    append = "append"
    commit = "commit"
    plot_data = "plot_data"


def format_event(type: EventType, data: str):
    return f"event: {type.value}\ndata: {data}\n\n"


@lru_cache(maxsize=1)
def _engine() -> LayerEngine:
    engine = (os.getenv("PANGE_ENGINE") or "in_memory").strip().lower()
    if engine == "duckdb":
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


def _apply_lod_cached(*, layers, aoi: BBox, view_zoom: float, highlight_point_ids: set[str] | None):
    """
    Cache LOD output by tile coverage and zoom bucket.

    This is primarily used by `/plot` refreshes on pan/zoom and should make them cheap.
    """
    tile_zoom = tile_zoom_for_view_zoom(view_zoom)
    tiles = tuple(sorted(tiles_for_bbox(tile_zoom, aoi), key=lambda t: (t[1], t[2])))
    zoom_bucket = int(round(float(view_zoom) * 2.0))  # 0.5 zoom buckets
    highlight_key = tuple(sorted(highlight_point_ids or ()))
    key = (tile_zoom, zoom_bucket, tiles, highlight_key)

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
        highlight_point_ids=highlight_point_ids,
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

        ctx = MapContext(
            aoi=aoi,
            view_center={"lat": thread.map.view.center.lat, "lon": thread.map.view.center.lon},
            view_zoom=thread.map.view.zoom,
        )

        result = _engine().get(ctx)
        aoi_layers = result.layers
        index = result.index

        response = route_prompt(prompt, layers=aoi_layers, index=index, aoi=aoi)

        # Stream a short explanation.
        for word in response.message.replace("\n", " \n ").split():
            yield format_event(EventType.append, word)
            await sleep(0.02)

        (lod_layers, beer_clusters), cache_stats = _apply_lod_cached(
            layers=aoi_layers,
            aoi=aoi,
            view_zoom=thread.map.view.zoom,
            highlight_point_ids=response.highlight.point_ids if response.highlight is not None else None,
        )

        # Send the map payload before commit so frontend attaches it to the message.
        plot = build_prague_plot(
            lod_layers,
            highlight=response.highlight,
            aoi=aoi,
            view_center=ctx.view_center,
            view_zoom=ctx.view_zoom,
            focus_map=response.focus_map,
            beer_clusters=beer_clusters,
        )
        try:
            plot["layout"]["meta"]["stats"]["cache"] = cache_stats
        except Exception:
            pass
        yield format_event(EventType.plot_data, json.dumps(plot))

        # Commit the message (punctuation ends the buffer on frontend).
        yield format_event(EventType.commit, ".")
    except Exception as e:
        # Fail safe: return an error message but keep streaming protocol valid.
        msg = f"Backend error: {type(e).__name__}: {e}"
        for word in msg.split():
            yield format_event(EventType.append, word)
        yield format_event(EventType.commit, ".")
