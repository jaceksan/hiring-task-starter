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

