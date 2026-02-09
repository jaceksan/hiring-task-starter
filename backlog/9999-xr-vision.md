## Ultimate vision: XR (Quest/AR) interface for the geospatial agent

### What’s strong about the vision

- **Right fit for “agent + map”**: spatial reasoning + conversational control is a natural XR interaction model (hands/voice instead of mouse/keyboard).
- **Performance alignment**: the work we already want (MVT/tile-first, budgets/LOD, deterministic policies) becomes *mandatory* in XR, so the roadmap is coherent.

### Recommended framing (pragmatic end-state)

Keep the current app as the “2D cockpit”, and add an **XR mode** that reuses the same backend contracts:

- **Backend** remains FastAPI-based, serving:
  - agent responses (streaming)
  - telemetry
  - **tile endpoints** (vector + optional raster)
- **Frontend** becomes “multi-surface”:
  - 2D web UI (current)
  - XR UI (WebXR) using GPU-first rendering

This avoids a big-bang rewrite and keeps the demo usable on normal browsers.

### UI stack: Three.js + WebGPU (and WebXR) — yes, with a staged migration

- **Three.js** is a practical default for XR because it has mature WebXR support and a huge ecosystem.
- **WebGPU** is a good direction for long-term performance (dense lines, 3D extrusions), but you should plan:
  - WebGPU as a fast path,
  - WebGL2 fallback (especially for browser variability).

**Staged approach**:

1. Add tile-first data delivery (MVT) to backend (already planned).
2. In 2D, render MVT efficiently (keeps parity and proves the data path).
3. Add XR scene rendering of the same layers (Quest browser via WebXR).
4. Only then explore “full UI migration” away from Plotly for scenarios that benefit.

### Data delivery: vector tiles first; raster tiles selectively

- **Vector tiles (MVT)** should be the primary path for roads/water/places because:
  - you need dynamic styling + LOD in the client,
  - you can keep payloads bounded per tile.
- **Raster tiles** can still be useful for heavy polygon shading / heatmaps / large coverages.

About “Python TiTiler”:

- **TiTiler is great for raster** (COGs, imagery, hillshade, etc.).
- For **vector tiles**, you’ll likely want a dedicated path (either build your own MVT endpoint in FastAPI for GeoParquet/DuckDB, or introduce a vector tile server later).

### Hand tracking

For Oculus/Quest via browser, plan around WebXR capabilities:

- **WebXR + Hand Input** (hand joints) where available.
- Provide a controller fallback.

Interaction design that tends to work:

- grab/pan/scale the map plane with two-hand gestures
- laser-pointer selection as fallback
- “pin” a POI or region of interest and let the agent operate on that AOI

### Voice to text

- Start with **client-side speech-to-text** (where supported) and send text as normal prompt input.
- Keep a “push-to-talk” UX to avoid accidental capture.
- Add server-side speech later only if you need consistent cross-device behavior.

### XR-specific product ideas (extensions to your vision)

- **AOI-as-object**: the viewport becomes a manipulable 3D bounding volume; agent queries reference it explicitly (“analyze within this box”).
- **Time slider / scenario playback**: flood extent or infrastructure changes over time as an immersive “story”.
- **3D extrusions**: buildings/population intensity as height, with LOD and tile budgets.
- **Collaborative mode**: multiple users in the same scene, shared AOIs and agent responses (later, via WebRTC/WebSocket sync).

### Backend implications (what changes)

- Tile endpoints become first-class (vector + optional raster).
- Stronger emphasis on determinism:
  - stable per-zoom policies,
  - strict per-tile feature budgets,
  - telemetry per tile request.
- Optional: switch some streaming from SSE to WebSocket if XR interactions demand higher-frequency updates (not required initially).

