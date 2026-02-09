## Backlog (ordered)

The order of items below is the priority order (top = highest). Each item has up to three concise sub-bullets; when needed, the last sub-bullet links to a detail file in `backlog/`.

- **P2 — Stabilize Scenario A performance (GeoParquet + Plotly baseline)**
  - Use telemetry to isolate bottlenecks (`duckdbMs` vs `decodeMs` vs `jsonSerialize`) and tighten budgets/LOD deterministically.
  - Prefer changes that reduce decoded geometry volume (candidates, simplification, pre-aggregation) rather than only UI tweaks.
  - Details: [`backlog/0100-scenario-a-performance.md`](backlog/0100-scenario-a-performance.md)

- **P2 — Highlighting roadmap (make LOD/budgets understandable and correct)**
  - Fix/clarify incomplete highlight due to LOD/budgets (bigger highlight budget or deterministic subsample + explicit message).
  - Support multiple simultaneous highlight overlays, clarify modes, and add follow-up demos (escape roads near places, polygon intensity shading).
  - Details: [`backlog/0101-highlighting-roadmap.md`](backlog/0101-highlighting-roadmap.md)

- **P2 — Scenario B: implement MVT/vector-tile scenario (massive layers)**
  - Add backend tile endpoint + per-layer tile query policy; render in frontend as a vector tile overlay.
  - Decide/implement geometry preprocessing to avoid problematic WKB variants (e.g. `UNKNOWN M`) and keep tiles deterministic.
  - Details: [`backlog/0200-mvt-scenario.md`](backlog/0200-mvt-scenario.md)

- **P2 — Replace small layers in the largest scenario with larger equivalents (same use case)**
  - Prefer water + places; download larger datasets if they exist and update `scenario.yaml` accordingly.
  - Re-measure end-to-end refresh and payload sizes after the swap.
  - Details: [`backlog/0201-larger-layers.md`](backlog/0201-larger-layers.md)

- **P3 — Evaluate GeoArrow for the GeoParquet/DuckDB pipeline**
  - Explore whether Arrow-native geometry transport/decoding can reduce WKB decode cost and Python overhead.
  - Identify the smallest experiment that provides signal (one layer, one query path).
  - Details: [`backlog/0300-geoarrow-evaluation.md`](backlog/0300-geoarrow-evaluation.md)

- **P3 — Adopt backend type checking with Astral “ty”**
  - Add `ty` to backend tooling, run it in CI/local `make` targets, and fix reported issues.
  - Decide the “typed enough” bar (modules required to be clean vs allowed exceptions).
  - Details: [`backlog/0301-backend-ty-typechecking.md`](backlog/0301-backend-ty-typechecking.md)

- **P4 — Preserve a readable project context snapshot (ex-`PROJECT_CONTEXT.md`)**
  - Keep architecture/decisions documented without bloating `BACKLOG.md`.
  - Update it only when decisions change materially (scenario strategy, engine interfaces, perf approach).
  - Details: [`backlog/0000-project-context.md`](backlog/0000-project-context.md)

- **P∞ — Ultimate vision: XR (Quest/AR) interface for geospatial “agent”**
  - Add an immersive WebXR mode (VR/MR) with hand tracking and voice-to-text queries.
  - Migrate rendering toward GPU-first (Three.js + WebGPU) and tile-first data delivery (vector/raster tiles).
  - Details: [`backlog/9999-xr-vision.md`](backlog/9999-xr-vision.md)

