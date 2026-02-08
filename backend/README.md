# Backend

In `main.py` you will find a FastAPI endpoint definition `POST /invoke` which is called by the frontend when a new prompt is submitted. It receives the whole thread and the last message is the just submitted prompt. When connecting your LLM logic, use the `handle_incoming_message` function which streams back different events to frontend:

- `append` adds text to buffer on frontend
- `commit` adds text to and commits the buffer
- `plot_data` send stringified JSON with Plotly data

Note: this MVP expects an AOI viewport bbox to be sent by the frontend in the request body as `map.bbox` (`minLon`, `minLat`, `maxLon`, `maxLat`).

## How to run

You need `Python` installed and `uv` ideally

```bash
uv venv # Create virtual environment
uv add -r requirements.txt # installs the dependencies
uv run fastapi dev main.py # starts the app on port 8000
```
