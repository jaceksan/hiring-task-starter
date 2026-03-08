## Backlog (ordered)

The order of items below is the priority order (top = highest). Each item has up to three concise sub-bullets; when needed, the last sub-bullet links to a detail file in `backlog/`.

- **P2 — Highlighting roadmap (make the CZ “flood” demo fully working)**
  - The CZ experience is stable for “How many places are flooded?”, but remaining supported questions are not validated yet.
  - Test all remaining questions, then remove weak ones or update their behavior so each supported question works reliably end-to-end.
  - Details: [`backlog/0101-highlighting-roadmap.md`](backlog/0101-highlighting-roadmap.md)

- **P2 — Scenario B: implement MVT/vector-tile scenario (massive layers)**
  - Move heavy CZ base geometry (`roads`, `flood_zones`, dense polygons) to vector tiles, keeping Plotly for interactive highlights/markers.
  - Prefer precomputed multi-zoom tiles (Google/Seznam style) with deterministic geometry preprocessing/generalization and class visibility by zoom.
  - Define perf targets (CZ zoom bands, p95 response/render) and use cache-friendly tile serving/versioning.
  - Details: [`backlog/0200-mvt-scenario.md`](backlog/0200-mvt-scenario.md)

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

