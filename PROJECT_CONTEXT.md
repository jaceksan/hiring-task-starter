# Hiring task repo — context + remaining plan

## Context (read this first)

### What this project demonstrates
A React + FastAPI demo of “agent-driven geospatial analysis”: user asks questions in natural language, backend runs deterministic geo reasoning on a few map layers, and streams back:
- chat messages (SSE `append`/`commit`)
- map updates (`plot_data`) rendered with Plotly/Mapbox

Core “PangeAI-ish” value:
- combine heterogeneous layers (points/lines/polygons)
- query by **Area Of Interest** (viewport bbox)
- keep UX responsive via **LOD** (clustering/simplification) + **budgets**
- scale to larger datasets via **DuckDB + GeoParquet** (and next: vector tiles)
- record **telemetry** to understand perf regressions

### Big decision: two-scenario approach (current + “next-gen”)
We decided to keep **two scenarios**:

- **Scenario A (current, fixed)**: `czech_population_infrastructure_large`
  - still uses DuckDB + GeoParquet + Plotly traces
  - goal: show fast refresh via AOI caching + LOD + YAML-driven “render policy”
  - this scenario is the baseline you can demo immediately

- **Scenario B (next, heavy layers)**: a new **MVT/vector-tile** scenario
  - goal: show the “novel” approach for truly massive line/polygon layers (roads/water) using tile-based rendering
  - will likely add a tile endpoint (e.g. `/tiles/{scenarioId}/{layerId}/{z}/{x}/{y}.mvt`) and render as a vector overlay in the frontend
  - note: current GeoParquet roads contain some WKB geometries DuckDB spatial can’t parse (`UNKNOWN M`), so MVT may require regenerating/normalizing geometry (or a different preprocessing pipeline)

### Repo structure (mental model)
- **backend**
  - FastAPI app: `/invoke`, `/plot`, `/scenarios`, `/telemetry/*`
  - engines:
    - `in_memory`: loads features in Python + STRtree slicing
    - `duckdb`: seeded mode for “small”, GeoParquet query-on-read for “large”
  - scenario registry: `scenarios/*/scenario.yaml`
  - routing: keyword-based “agent” rules in YAML (no external LLM required)
  - LOD: clustering/simplification + hard budgets
  - telemetry store: DuckDB-backed, persistent, supports reset + aggregated views

- **frontend**
  - map-first layout + scenario dropdown + engine dropdown
  - Playwright e2e as the only frontend test suite

### What was changed recently (important for the plan)
- GeoParquet querying moved under:
  - `backend/engine/duckdb_impl/geoparquet/`
    - `bundle.py`: per-scenario layer loop + AOI/zoom cache
    - `layer.py`: per-layer query orchestration
    - `sql.py`: DuckDB queries
    - `decode.py`: WKB -> features
    - `policy.py`: YAML policy helpers
    - `bbox.py`: bbox column detection
- Large scenario now has YAML-driven prefiltering/caps:
  - `scenarios/czech_population_infrastructure_large/scenario.yaml` → `source.geoparquet.renderPolicy`
  - roads/water render at low zoom by decoding only “important” classes and capping candidates
- Telemetry improvements:
  - `layout.meta.stats.timingsMs` now includes `jsonSerialize`
  - `layout.meta.stats.engineStats` includes per-layer GeoParquet stats (duckdbMs/decodeMs/counts)
  - highlight stats include `highlightRequested` / `highlightRendered`

### Data reality (why roads are hard)
- `cz_bbox/roads.parquet` is ~1.87M features; dominant `fclass` values are footway/service/residential/path.
- Frontend Plotly traces are not meant to ship/render hundreds of thousands of line geometries in one payload.
- Therefore: (A) configurable “render policy” + (B) tile-based rendering for the next scenario.

### How to validate quickly
- `make lint-backend`
- `make types-all`
- `make test-backend`
- (optional) `make test-e2e-frontend` when UI/map behavior changes

---

## Remaining TODOs (concise plan)

### A) Speed of iteration / tooling
- [ ] Consider adding Astral’s type checker (“ty”) for backend typing checks

### B) Performance (Scenario A: GeoParquet + Plotly)
- [ ] Manually test `czech_population_infrastructure_large` scenario end-to-end and fix any issues found
- [ ] Investigate remaining high-zoom slowness (if still present):
  - use `engineStats` per-layer timing (`duckdbMs`, `decodeMs`) and `timingsMs.jsonSerialize`
  - ensure query count is minimized and caching behaves as expected
  - optimize further (batching, pre-aggregations, tile materialization strategy)
- [ ] Evolve “importance/LOD policy” (YAML-configurable) beyond the first cut:
  - roads: refine class progression; consider bbox-size ranking and deterministic “drop” messaging
  - water: add area-based thresholds (not only fclass) for low zoom readability
  - formalize per-layer budgets/caps + deterministic drop rules when budgets exceeded
  - keep it per-scenario/per-layer in YAML

### C) Highlighting roadmap
- [ ] Fix/clarify “incomplete road highlight due to LOD/budgets”:
  - allocate a larger budget for highlight overlays, OR deterministic subsample
  - always message: “matched X, rendering Y due to budget”
  - ensure multi-line highlights don’t silently collapse to 1 feature
- [ ] Support multiple simultaneous highlight overlays
- [ ] Two highlight modes (question-triggered vs static toggles)
- [ ] “Escape roads near highlighted places” demo use case (YAML-driven)
- [ ] Follow-up demo: polygon “intensity” shading

### D) New scenario (Scenario B: heavy layers via MVT/vector tiles)
- [ ] Implement a new MVT-based scenario to demonstrate truly massive layers:
  - backend tile endpoint + per-layer tile query policy
  - frontend vector tile overlay rendering
  - decide and implement geometry preprocessing to avoid `UNKNOWN M` WKB issues

### Cleanup
- [ ] Delete `PROJECT_CONTEXT.md` once we are done (cleanup)

