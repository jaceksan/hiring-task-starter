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

    lod_layers, beer_clusters = apply_lod(
        aoi_layers,
        view_zoom=ctx.view_zoom,
        highlight_point_ids=set(body.highlight.get("pointIds") or [])
        if body.highlight
        else None,
    )

    highlight = None
    if body.highlight and body.highlight.get("pointIds"):
        from plotly.build_plot import Highlight as PlotHighlight

        highlight = PlotHighlight(
            point_ids=set(body.highlight.get("pointIds") or []),
            title=body.highlight.get("title") or "Highlighted",
        )

    return build_prague_plot(
        lod_layers,
        highlight=highlight,
        aoi=aoi,
        view_center=ctx.view_center,
        view_zoom=ctx.view_zoom,
        focus_map=False,
        beer_clusters=beer_clusters,
    )


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

        lod_layers, beer_clusters = apply_lod(
            aoi_layers,
            view_zoom=thread.map.view.zoom,
            highlight_point_ids=response.highlight.point_ids
            if response.highlight is not None
            else None,
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
        yield format_event(EventType.plot_data, json.dumps(plot))

        # Commit the message (punctuation ends the buffer on frontend).
        yield format_event(EventType.commit, ".")
    except Exception as e:
        # Fail safe: return an error message but keep streaming protocol valid.
        msg = f"Backend error: {type(e).__name__}: {e}"
        for word in msg.split():
            yield format_event(EventType.append, word)
        yield format_event(EventType.commit, ".")
