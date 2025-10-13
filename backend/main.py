from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json
from pydantic import BaseModel
from enum import Enum
from asyncio import sleep

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


async def handle_incoming_message(thread: ApiThread):
    last_message = thread.messages[-1]

    example_messages_1 = [
        "Hello, this is an example message, just to showcase the events",
        f'You said: "{last_message.text}" and I think it\'s beautiful',
    ]

    for message in example_messages_1:
        await sleep(1)
        for word in message.split(" "):
            yield format_event(EventType.append, word)
            await sleep(0.1)
        yield format_event(EventType.commit, ".")

    await sleep(1)
    yield format_event(EventType.plot_data, json.dumps(get_example_plot_data()))

    example_messages_2 = ["Go checkout the backend/main.py file and add your own logic"]

    for message in example_messages_2:
        await sleep(1)
        for word in message.split(" "):
            yield format_event(EventType.append, word)
            await sleep(0.1)
        yield format_event(EventType.commit, ".")


def get_example_plot_data():
    # Plotly structure
    return {
        "data": [
            {
                "type": "scattermapbox",
                "mode": "text+markers",
                "lat": [37.77, -23.55, 48.85, 35.68],
                "lon": [-122.42, -46.63, 2.35, 139.69],
                "text": ["San Francisco", "São Paulo", "Paris", "Tokyo"],
                "textposition": "top right",
                "marker": {"size": 12, "color": "red"},
            },
        ],
        "layout": {
            "mapbox": {
                "center": {"lat": 48.85, "lon": 2.35},
                "zoom": 4,
                "style": "carto-positron",
            },
        },
    }
