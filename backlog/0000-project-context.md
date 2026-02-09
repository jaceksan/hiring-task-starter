## Project context (snapshot)

This file preserves the original long-form context from `PROJECT_CONTEXT.md`, so `BACKLOG.md` can stay concise.

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

We keep **two scenarios**:

- **Scenario A (current, fixed)**: `czech_population_infrastructure_large`
  - uses DuckDB + GeoParquet + Plotly traces
  - goal: show fast refresh via AOI caching + LOD + YAML-driven “render policy”
  - baseline you can demo immediately

- **Scenario B (next, heavy layers)**: a new **MVT/vector-tile** scenario
  - goal: show a tile-based approach for truly massive line/polygon layers (roads/water)
  - likely adds a tile endpoint like `/tiles/{scenarioId}/{layerId}/{z}/{x}/{y}.mvt` and renders as a vector overlay in the frontend
  - note: current GeoParquet roads include some WKB variants DuckDB spatial can’t parse (`UNKNOWN M`), so MVT may require regenerating/normalizing geometry (or a different preprocessing pipeline)

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

### Recent changes that matter

- GeoParquet querying lives under `backend/engine/duckdb_impl/geoparquet/`:
  - `bundle.py`: per-scenario layer loop + AOI/zoom cache
  - `layer.py`: per-layer query orchestration
  - `sql.py`: DuckDB queries
  - `decode.py`: WKB -> features
  - `policy.py`: YAML policy helpers
  - `bbox.py`: bbox column detection
- Large scenario has YAML-driven prefiltering/caps:
  - `scenarios/czech_population_infrastructure_large/scenario.yaml` → `source.geoparquet.renderPolicy`
- Telemetry includes:
  - `layout.meta.stats.timingsMs.jsonSerialize`
  - `layout.meta.stats.engineStats` per-layer GeoParquet stats (`duckdbMs`/`decodeMs`/counts)
  - highlight stats: `highlightRequested` / `highlightRendered`

### Data reality (why roads are hard)

- `cz_bbox/roads.parquet` is ~1.87M features; dominant `fclass` values are footway/service/residential/path.
- Plotly traces are not designed to ship/render hundreds of thousands of line geometries in one payload.
- Therefore: (A) configurable “render policy” + (B) tile-based rendering for the next scenario.

