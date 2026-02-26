import asyncio

import pytest
from agent.router import AgentResponse
from engine.types import EngineResult
from geo.index import build_geo_index
from layers.types import Layer, LayerBundle, PointFeature
from main import (
    ApiBbox,
    ApiCenter,
    ApiMapContext,
    ApiMapView,
    ApiMessage,
    ApiMessageSenderEnum,
    ApiThread,
    handle_incoming_message,
)
from plotly.types import Highlight


@pytest.fixture(autouse=True)
def _disable_stream_delay(monkeypatch):
    async def _no_sleep(_seconds: float):
        return None

    monkeypatch.setattr("api.invoke_stream.sleep", _no_sleep)


@pytest.fixture(autouse=True)
def _use_fast_fake_engine(monkeypatch):
    layers = LayerBundle(
        layers=[
            Layer(
                id="places",
                kind="points",
                title="Places",
                features=[PointFeature(id="p1", lon=14.43, lat=50.07, props={})],
                style={},
                metadata={},
            ),
            Layer(
                id="roads",
                kind="lines",
                title="Roads",
                features=[],
                style={},
                metadata={},
            ),
            Layer(
                id="flood_zones",
                kind="polygons",
                title="Flood zones",
                features=[],
                style={},
                metadata={},
            ),
        ]
    )
    index = build_geo_index(layers)
    result = EngineResult(layers=layers, index=index, stats={})

    class _FakeEngine:
        def get(self, _ctx):
            return result

    monkeypatch.setattr("api.invoke_stream._engine", lambda _name: _FakeEngine())
    monkeypatch.setattr(
        "api.invoke_stream._resolve_engine_name_for_scenario",
        lambda **_kwargs: "in_memory",
    )


def test_invoke_stream_passes_request_context_to_router(monkeypatch):
    seen_context: dict | None = None

    def fake_route_prompt(*args, **kwargs):
        nonlocal seen_context
        seen_context = kwargs.get("request_context")
        return AgentResponse(message="ok")

    monkeypatch.setattr("api.invoke_stream.route_prompt", fake_route_prompt)

    thread = ApiThread(
        id=1,
        title="t",
        messages=[
            ApiMessage(
                id=1,
                author=ApiMessageSenderEnum.human,
                text="show layers",
            )
        ],
        map=ApiMapContext(
            bbox=ApiBbox(minLon=14.22, minLat=49.94, maxLon=14.70, maxLat=50.18),
            view=ApiMapView(center=ApiCenter(lat=50.0755, lon=14.4378), zoom=12.0),
            context={"floodRiskLevel": "medium"},
        ),
    )

    async def consume():
        async for _ in handle_incoming_message(thread):
            pass

    asyncio.run(consume())
    assert seen_context == {"floodRiskLevel": "medium"}


def test_invoke_stream_emits_required_event_types(monkeypatch):
    def fake_route_prompt(*args, **kwargs):
        return AgentResponse(message="ok")

    monkeypatch.setattr("api.invoke_stream.route_prompt", fake_route_prompt)
    thread = ApiThread(
        id=1,
        title="t",
        messages=[
            ApiMessage(
                id=1,
                author=ApiMessageSenderEnum.human,
                text="how many places are flooded?",
            )
        ],
        map=ApiMapContext(
            bbox=ApiBbox(minLon=14.22, minLat=49.94, maxLon=14.70, maxLat=50.18),
            view=ApiMapView(center=ApiCenter(lat=50.0755, lon=14.4378), zoom=12.0),
        ),
    )

    async def collect():
        seen = set()
        async for chunk in handle_incoming_message(thread):
            # chunk is SSE formatted text: "event: X\ndata: Y\n\n"
            if chunk.startswith("event:"):
                event_name = chunk.split("\n", 1)[0].split(":", 1)[1].strip()
                seen.add(event_name)
        return seen

    seen = asyncio.run(collect())
    assert {"append", "plot_data", "commit"}.issubset(seen)


def test_invoke_stream_flooded_count_includes_answer_text(monkeypatch):
    def fake_route_prompt(*args, **kwargs):
        return AgentResponse(message="I found 1 place in flood zones.")

    monkeypatch.setattr("api.invoke_stream.route_prompt", fake_route_prompt)
    thread = ApiThread(
        id=1,
        title="t",
        messages=[
            ApiMessage(
                id=1,
                author=ApiMessageSenderEnum.human,
                text="how many places are flooded?",
            )
        ],
        map=ApiMapContext(
            bbox=ApiBbox(minLon=14.22, minLat=49.94, maxLon=14.70, maxLat=50.18),
            view=ApiMapView(center=ApiCenter(lat=50.0755, lon=14.4378), zoom=12.0),
        ),
    )

    async def collect_text():
        parts: list[str] = []
        async for chunk in handle_incoming_message(thread):
            if chunk.startswith("event: append"):
                data = chunk.split("\n", 1)[1]
                if data.startswith("data:"):
                    parts.append(data.split(":", 1)[1].strip())
        return " ".join(parts)

    text = asyncio.run(collect_text())
    assert "Backend error" not in text
    assert "I found" in text


def test_invoke_stream_safest_with_reachable_roads_does_not_error(monkeypatch):
    def fake_route_prompt(*args, **kwargs):
        return AgentResponse(
            message="Safest nearby places with reachable roads: Place A, Place B."
        )

    monkeypatch.setattr("api.invoke_stream.route_prompt", fake_route_prompt)
    thread = ApiThread(
        id=1,
        title="t",
        messages=[
            ApiMessage(
                id=1,
                author=ApiMessageSenderEnum.human,
                text="show safest nearby places outside selected flood risk with reachable roads",
            )
        ],
        map=ApiMapContext(
            bbox=ApiBbox(minLon=14.22, minLat=49.94, maxLon=14.70, maxLat=50.18),
            view=ApiMapView(center=ApiCenter(lat=50.0755, lon=14.4378), zoom=12.0),
        ),
    )

    async def collect_text():
        parts: list[str] = []
        async for chunk in handle_incoming_message(thread):
            if chunk.startswith("event: append"):
                data = chunk.split("\n", 1)[1]
                if data.startswith("data:"):
                    parts.append(data.split(":", 1)[1].strip())
        return " ".join(parts)

    text = asyncio.run(collect_text())
    assert "Backend error" not in text


def test_invoke_stream_reports_matched_vs_rendered_when_clipped(monkeypatch):
    def fake_route_prompt(*args, **kwargs):
        return AgentResponse(
            message="placeholder",
            highlight=Highlight(layer_id="places", feature_ids={"x1"}, title="H"),
            highlights=[
                Highlight(
                    layer_id="places", feature_ids={"x1"}, title="H", mode="prompt"
                )
            ],
        )

    def fake_build_map_plot(*args, **kwargs):
        return {
            "data": [],
            "layout": {
                "meta": {
                    "stats": {
                        "highlightRequested": 10,
                        "highlightRendered": 3,
                    }
                }
            },
        }

    monkeypatch.setattr("api.invoke_stream.route_prompt", fake_route_prompt)
    monkeypatch.setattr("api.invoke_stream.build_map_plot", fake_build_map_plot)

    thread = ApiThread(
        id=1,
        title="t",
        messages=[
            ApiMessage(
                id=1,
                author=ApiMessageSenderEnum.human,
                text="highlight motorways",
            )
        ],
        map=ApiMapContext(
            bbox=ApiBbox(minLon=14.22, minLat=49.94, maxLon=14.70, maxLat=50.18),
            view=ApiMapView(center=ApiCenter(lat=50.0755, lon=14.4378), zoom=12.0),
        ),
    )

    async def collect_text():
        parts: list[str] = []
        async for chunk in handle_incoming_message(thread):
            if chunk.startswith("event: append"):
                data = chunk.split("\n", 1)[1]
                if data.startswith("data:"):
                    parts.append(data.split(":", 1)[1].strip())
        return " ".join(parts)

    text = asyncio.run(collect_text())
    assert "Highlights: matched 10, rendering 3 due to budget." in text
