# Hiring task repo — high-signal summary (what we built + what’s left)

## What this project is about
A React + FastAPI demo of “agent-driven geospatial analysis”: user asks questions in natural language, backend does deterministic geo reasoning on a few map layers, and streams back:
- chat messages (SSE `append`/`commit`)
- map updates (`plot_data`) rendered with Plotly/Mapbox

The core “PangeAI-ish” value demonstrated:
- combine heterogeneous layers (points/lines/polygons)
- query by **Area Of Interest** (viewport bbox)
- keep UX responsive via **LOD** (clustering/simplification) + **budgets**
- optionally switch to **DuckDB + GeoParquet** for larger datasets
- record and inspect **telemetry** to understand perf regressions

## Repo structure (current mental model)
- backend/
  - FastAPI app exposing `/invoke`, `/plot`, `/scenarios`, telemetry endpoints
  - engines:
    - `in_memory`: loads layers into Python structures + Shapely STRtree
    - `duckdb`: queries GeoParquet via DuckDB; caching + safer concurrency patterns
  - scenario registry: discovers `scenarios/*/scenario.yaml`
  - generic plot builder producing Plotly payloads + `layout.meta.stats`
  - routing: keyword/pattern-based “agent” rules driven by YAML (no external LLM required)
  - LOD: point clustering, line/polygon simplification, strict caps (“budgets”)
  - AOI/tile caches: slippy-tile slicing + zoom-bucketed LOD caches
  - telemetry store: DuckDB-backed, persistent, includes reset + aggregated views
- frontend/
  - single-page, map-first UX:
    - left: threads list
    - top bar: scenario dropdown + engine dropdown + telemetry controls + reset
    - main: map (legend embedded into map)
    - bottom: chat drawer (collapsible; designed to not hide map too much)
  - Playwright e2e tests for basic interaction + persistence (adjusted for drawer)
- scenarios/
  - `prague_transport` (Prague “Flood & Transport”)
  - `prague_population_infrastructure_small` (GeoParquet small Prague bbox: roads/water/places)
  - `czech_population_infrastructure_large` (GeoParquet whole CZ bbox: roads/water/places)
- data/
  - `data/derived/.../prague_bbox/*.parquet` committed (small fixtures for tests)
  - `data/derived/.../cz_bbox/*.parquet` ignored (large files)

## Key product behaviors implemented
- **Scenario packs**: switching scenario swaps layer set + defaults
- **Engine selection**: dropdown; “in-memory” disabled when scenario requires GeoParquet (and/or labeled large)
- **AOI-first**: requests include bbox; engine slices by AOI
- **Automatic LOD on zoom/pan**: clusters at low zoom, raw points at high zoom; simplify lines/polys
- **Tile + zoom-bucket caching**: pan/zoom reuses cached tile slices + LOD outputs
- **Budget hardening**: payload never exceeds caps even in worst cases
- **Highlighting**:
  - question-triggered highlight for points (“show flooded places” style)
  - question-triggered highlight for lines (“highlight motorways”)
  - highlight stability: prevent `/plot` refresh races from overwriting highlights
  - highlight kept through LOD (within limits)
- **Telemetry**:
  - persistent store in DuckDB
  - reset button + aggregated UI panel (slowest calls, summary)
  - safe read access considerations (read-only / lock avoidance handled)

## Tests (current approach)
- backend: pytest
  - fast unit tests by default
  - `@pytest.mark.integration` for “slow/heavy/real decoding” paths
- frontend: Playwright e2e (headless)
  - helpers to open drawer + disable auto-minimize in tests
  - expectations adjusted to current copy + trace names

## Important constraints / conventions
- MVP repo: **backward compatibility is NOT required** (breaking changes OK; local restarts assumed)
- `.cursorignore` intentionally ignores `data/**/*` to keep Cursor fast (even if small fixtures are committed)

---

## TODOs (most important first: “speed of development” + correctness blockers)

### A) Speed of iteration / tooling
1) Create root `Makefile` with targets:
   - `lint`, `types`, `test`, `test-integration` for backend + frontend
   - consider adding Astral’s type checker (“ty”) for backend typing checks
   - update `.cursor/rules/general.mdc` to instruct running `make …` for validations

2) Keep backend tests fast:
   - ensure slow/heavy tests are under `-m integration`
   - keep unit suite consistently < ~5s

3) Frontend test strategy:
   - keep Playwright e2e stable + minimal
   - decide if any unit tests are worth it (likely optional for demo)

### B) Performance (large GeoParquet scenario still has slow paths)
4) Investigate why GeoParquet mode can still take ~7s at high zoom:
   - add deeper telemetry breakdown (DuckDB scan vs geometry decode vs Python transforms vs plot build)
   - confirm query count minimized (avoid “tens of queries per view” patterns)
   - optimize further (batching, pre-aggregations, tile materialization strategy)

5) Large-layers “importance/LOD policy” (YAML-configurable):
   - roads: show only higher classes at low/medium zoom, refine progressively
   - water: show only large polygons (area threshold) / selected types until zoomed in
   - caps + deterministic drop policy when budgets exceeded
   - make this per-scenario/per-layer in YAML

### C) Highlighting roadmap
6) Fix/clarify “incomplete road highlight due to LOD/budgets”:
   - when matched highlights exceed budgets, either:
     - allocate a larger budget for highlight overlays, OR
     - deterministic subsample, OR
     - message: “matched X, rendering Y due to budget”
   - ensure multi-line highlights don’t silently collapse to 1 feature

7) Support multiple simultaneous highlight overlays:
   - e.g., highlight flooded places (points) AND motorways (lines) together
   - extend plot meta model: array of highlight overlays
   - update frontend to preserve/merge highlights across actions

8) Two highlight modes:
   - (1) triggered by question
   - (2) static on/off overlays in map UI (useful for roads/water)
   - design YAML + UI + payload model so both can coexist

9) “Escape roads near highlighted places” demo use case:
   - show closest roads to highlighted points
   - decide: one road per place vs one global best set/route
   - keep it YAML-driven

10) Follow-up demo: polygon “intensity” shading:
   - shaded polygons by numeric intensity (legend included)
   - add scenario + prompt + styling rules in YAML

### D) UX / data modeling cleanup
11) Scenario-scoped threads:
   - when switching scenario, thread list + chat should show only threads for that scenario
   - decide if API paths include scenarioId or only payload param
   - update local storage schema/migrations accordingly

12) Example prompts should be scenario-specific:
   - store `examplePrompts` in scenario YAML
   - UI should swap examples when scenario changes
   - add a TODO/examples authoring workflow

### E) Data/fixtures policy (mostly resolved, keep guardrails)
13) Derived data policy:
   - keep small Prague GeoParquet fixtures committed for reproducible tests
   - keep whole-CZ derived data ignored
   - ensure `.gitignore` remains correct as datasets evolve

---

## Notes / decisions made along the way
- Prague “transport realism”: keep metro + tram lines distinct colors; stations/stops as points with hover; “safe pubs” ranking prefers metro, tram as fallback.
- Zoom/focus behavior: focus should prefer viewport-local results; avoid zooming out to global extent when enough candidates exist in current AOI.
- DuckDB stability: avoid unsafe concurrency; prioritize “safe + fast enough” over max parallelism.

## Current ask from you (when starting the next chat)
- Pick which TODO cluster to tackle next:
  - fastest dev-speed win: Makefile + rules + test split
  - biggest product win: multi-highlight overlays + static toggles
  - biggest engineering win: large scenario perf redesign (reduce query count + importance/LOD policy)

