## Scenario B: MVT/vector tiles

### Goal

Render massive base geometry (especially CZ `roads`/`flood_zones`) as vector tiles instead of Plotly traces, so map refresh remains fast across zoom levels.

### Target architecture (aligned with Google/Seznam style)

- Use **precomputed multi-zoom vector tiles** for heavy, mostly static layers.
- Keep Plotly for dynamic overlays (highlights, selected features, point markers, chat-driven emphasis).
- Treat on-demand tile generation as fallback/prototype path only.

### Sketch

- Backend:
  - `/tiles/{scenarioId}/{layerId}/{z}/{x}/{y}.mvt`
  - tile policy per layer (filters + class thresholds + visibility by zoom + deterministic feature limits)
  - preprocessing pipeline for geometry normalization/generalization to avoid problematic WKB variants (e.g. `UNKNOWN M`)
  - tile packaging/versioning (for example MBTiles/PMTiles) and cache-friendly serving
- Frontend:
  - render MVT as a vector overlay, with Plotly kept for markers/highlights/annotations

### Preprocessing requirements

- Per-zoom simplification budgets tuned by layer/class (roads are the critical path).
- Stable feature IDs across zoom levels to preserve hover/highlight consistency.
- Deterministic tile content for the same source + config revision.
- Explicit rules for class visibility by zoom (motorway/trunk/primary/...).

### Performance acceptance criteria

- Define CZ targets by zoom band (wide, medium, city detail).
- Track p95 for:
  - tile response latency,
  - first meaningful roads paint,
  - map refresh completion with overlays.
- Validate that enabling additional road classes does not introduce multi-second spikes.

### Migration boundary

- Phase 1: move base heavy geometry to MVT.
- Phase 2: keep query-driven overlays in Plotly and ensure visual parity with current UX.
- Phase 3: evaluate whether more overlay classes should also move to tiles.

### Note on “Option B” (per-layer async loading)

The “split `/plot` by layer” idea becomes **more feasible and more natural** with MVT:

- the transport is already **per-layer/per-tile** (each layer is its own tile source URL)
- browsers fetch tiles concurrently and incrementally by design (no Plotly trace merge needed)
- telemetry grouping can shift from a `refreshId` to “tile request” aggregation (per layer / per z/x/y)

