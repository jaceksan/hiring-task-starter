## Explore splitting `/plot` by layer (generic async loading)

### Status

Discovery / requirements clarification (do not implement until we agree on feasibility + UX contract).

### Goal

Split the current “all layers in one `/plot` call” model into **generic per-layer calls**, so slow layers don’t block fast ones.

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

### Key feasibility questions

- Can we guarantee stable trace identity per layer in Plotly (so merges are safe)?
- Does the backend already build per-layer traces independently (or do layers depend on each other for LOD/budgets)?
- Do we want to keep “single-call mode” as fallback (likely yes)?

