## Scenario B: MVT/vector tiles

### Goal

Render massive line/polygon layers (roads/water) as tiles instead of Plotly traces.

### Sketch

- Backend:
  - `/tiles/{scenarioId}/{layerId}/{z}/{x}/{y}.mvt`
  - tile query policy per layer (filters + class thresholds + max features)
  - geometry normalization/preprocessing to avoid problematic WKB variants (e.g. `UNKNOWN M`)
- Frontend:
  - render MVT as a vector overlay (keep Plotly for markers/annotations if needed)

### Note on “Option B” (per-layer async loading)

The “split `/plot` by layer” idea becomes **more feasible and more natural** with MVT:

- the transport is already **per-layer/per-tile** (each layer is its own tile source URL)
- browsers fetch tiles concurrently and incrementally by design (no Plotly trace merge needed)
- telemetry grouping can shift from a `refreshId` to “tile request” aggregation (per layer / per z/x/y)

