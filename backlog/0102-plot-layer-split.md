## Explore splitting `/plot` by layer (generic async loading)

### Status

Investigated (higher complexity than it initially appears; see “Complexity & pitfalls”).

### Goal

Split the current “all layers in one `/plot` call” model into **generic per-layer calls**, so slow layers don’t block fast ones.

### Current architecture (what we have today)

- Backend `/plot` does (in order):
  - `engine.get(ctx)` (for large scenarios: GeoParquet → queries *all* GeoParquet layers)
  - `_apply_lod_cached(...)` (LOD + clustering; cache key is based on tile coverage + zoom bucket + highlight)
  - `build_map_plot(lod_layers, ...)` which:
    - emits traces in stable order: polygons → lines → points (+ clusters for the highlight layer)
    - optionally emits a highlight trace that depends on the layer bundle
  - returns a single Plotly payload (`data[]`, `layout{...}`) with `layout.meta.stats` timings + engineStats
- Frontend calls `/plot` on pan/zoom (debounced) and **replaces** the Plotly payload, while preserving map view (center/zoom) client-side.

### Proposed API shape (sketch)

- Keep `/plot` but add a query parameter such as:
  - `?layerId=<id>` → return traces for a single layer only
  - `?layerId=__all__` (default) → current behavior for compatibility/debugging
- Response should include enough metadata to allow incremental merge:
  - stable trace identity per layer (so we can replace just that layer’s traces)
  - per-layer timings + counts (telemetry)

### Frontend implications

- Fire N requests concurrently (best-effort).
- Merge traces incrementally without flicker:
  - preserve user view (already relies on `uirevision`)
  - ensure legend stability and trace IDs are deterministic
- Decide failure mode per layer:
  - missing layer → keep previous layer traces or drop them?
  - show “partial refresh” indicator

### Telemetry implications

- Telemetry becomes “many requests per refresh”.
- We need an aggregation concept:
  - a client-generated `refreshId` passed to each request so backend can group
  - UI should show per-layer durations and overall perceived refresh time

### Complexity & pitfalls (what can bite us)

- **Backend load can get worse, not better**
  - If we naïvely “split” the endpoint but each call still runs `engine.get(ctx)` for *all* layers, we multiply the expensive work by N.
  - We need a real **per-layer fetch path** in the engine (or server-side parallelization behind one request).
- **LOD/clustering/highlight coupling**
  - Clustering is special-cased for one points layer and highlight depends on what’s present in the layer bundle.
  - With partial layer payloads, highlight can be temporarily wrong/missing unless we define ordering (e.g. fetch highlight layer first) or split highlight into its own request.
- **Plotly incremental merge is not free**
  - Today we replace the entire `data[]`. For incremental updates we need a deterministic way to identify traces belonging to a layer.
  - Without explicit trace IDs/groups, we risk **duplicate traces**, **legend churn**, and flicker.
- **Stale responses + map stability**
  - We already guard against stale full responses. With N in-flight requests we need per-layer staleness checks and abort fan-out.
  - Each partial update triggers a Plotly react; we must keep current “never override center/zoom” invariants.
- **Telemetry semantics change**
  - “One refresh” becomes multiple backend rows; without `refreshId` the panel becomes noisy and hard to interpret.

### Safer MVP options (recommended order)

- **Option A (lowest risk): keep single `/plot`, parallelize on the backend**
  - Query layers concurrently server-side (threads/async), then build one Plotly payload.
  - Keeps frontend simple and preserves current telemetry model.
- **Option B (true split): per-layer `/plot?layerId=...` with a merge contract**
  - Backend must:
    - fetch only that layer (or a small set)
    - return traces tagged with `layerId` (or deterministic `uid`/`legendgroup`)
    - accept `refreshId` for grouping telemetry
  - Frontend must:
    - maintain `{layerId -> traces}` and compose into one `data[]`
    - show “partial refresh” indicator and define what happens on failures/timeouts

### Recommendation

- Treat as **medium-high complexity**. Before implementing, we should pick **Option A** or **Option B** explicitly and write down the merge + telemetry contract.

### Key feasibility questions

- Can we guarantee stable trace identity per layer in Plotly (so merges are safe)?
- Does the backend already build per-layer traces independently (or do layers depend on each other for LOD/budgets)?
- Do we want to keep “single-call mode” as fallback (likely yes)?

