import asyncio

from main import ApiMessage, ApiMessageSenderEnum, ApiThread, handle_incoming_message


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

