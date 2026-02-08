import asyncio

from main import ApiBbox, ApiCenter, ApiMapContext, ApiMapView, ApiMessage, ApiMessageSenderEnum, ApiThread, handle_incoming_message


def test_invoke_stream_emits_required_event_types():
    thread = ApiThread(
        id=1,
        title="t",
        messages=[
            ApiMessage(
                id=1,
                author=ApiMessageSenderEnum.human,
                text="how many pubs are flooded?",
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


def test_invoke_stream_flooded_count_includes_answer_text():
    thread = ApiThread(
        id=1,
        title="t",
        messages=[
            ApiMessage(
                id=1,
                author=ApiMessageSenderEnum.human,
                text="how many pubs are flooded?",
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


def test_invoke_stream_dry_near_metro_does_not_error():
    thread = ApiThread(
        id=1,
        title="t",
        messages=[
            ApiMessage(
                id=1,
                author=ApiMessageSenderEnum.human,
                text="find 20 dry pubs near metro",
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

