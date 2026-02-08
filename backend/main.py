from __future__ import annotations

import json
from asyncio import sleep
from enum import Enum
from functools import lru_cache

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.router import route_prompt
from geo.ops import build_geo_index
from layers.load_prague import load_prague_layers
from plotly.build_plot import build_prague_plot

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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


class ApiThread(BaseModel):
    id: int
    title: str
    messages: list[ApiMessage]


@app.post("/invoke")
def invoke(body: ApiThread):
    return StreamingResponse(
        handle_incoming_message(body), media_type="text/event-stream"
    )


class EventType(str, Enum):
    append = "append"
    commit = "commit"
    plot_data = "plot_data"


def format_event(type: EventType, data: str):
    return f"event: {type.value}\ndata: {data}\n\n"


@lru_cache(maxsize=1)
def _layers_and_index():
    layers = load_prague_layers()
    index = build_geo_index(layers.flood_q100, layers.metro_ways)
    return layers, index


async def handle_incoming_message(thread: ApiThread):
    prompt = thread.messages[-1].text if thread.messages else ""

    try:
        layers, index = _layers_and_index()
        response = route_prompt(prompt, layers=layers, index=index)

        # Stream a short explanation.
        for word in response.message.replace("\n", " \n ").split():
            yield format_event(EventType.append, word)
            await sleep(0.02)

        # Send the map payload before commit so frontend attaches it to the message.
        plot = build_prague_plot(layers, highlight=response.highlight)
        yield format_event(EventType.plot_data, json.dumps(plot))

        # Commit the message (punctuation ends the buffer on frontend).
        yield format_event(EventType.commit, ".")
    except Exception as e:
        # Fail safe: return an error message but keep streaming protocol valid.
        msg = f"Backend error: {type(e).__name__}: {e}"
        for word in msg.split():
            yield format_event(EventType.append, word)
        yield format_event(EventType.commit, ".")
