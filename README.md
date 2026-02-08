# Hiring task starter

This is a repo with React frontend and Python backend to get you started on your task.

## MVP implemented in this repo (Prague Flood & Beer)

This repo now contains an MVP that fulfills the core requirements from `requirements.pdf`:

- For the **current** “what we built + what’s left” snapshot (including scenario packs, DuckDB/GeoParquet engine, LOD/budgets, telemetry), see `PROJECT_CONTEXT.md`.

- **Region**: Prague
- **3 datasets, different geometries**:
  - Flood extent Q100 (**polygons**) from IPR Praha (stored under `data/prague/`)
  - Metro geometry (**lines**) from OpenStreetMap/Overpass (stored under `data/prague/`)
  - Beer POIs (**points**) from OpenStreetMap/Overpass (stored under `data/prague/`)
- **Prompt-based “agent”**: backend performs lightweight spatial reasoning:
  - **point-in-polygon**: is a pub inside the flood extent?
  - **distance-to-line (meters)**: how close is a pub to the metro? (computed in a projected CRS)

### Example prompts

Try these in a thread:

- `show layers`
- `how many pubs are flooded?`
- `find 20 dry pubs near metro`
- `recommend 5 safe pubs`

### AOI-first (viewport) performance

This MVP now runs **AOI-first**: the frontend sends the current map viewport as a WGS84 bbox `(minLon, minLat, maxLon, maxLat)` with each prompt, and the backend:

- clips all 3 layers to that bbox before building Plotly traces
- computes answers (flooded count, “dry near metro”) only over AOI-sliced candidates

How to observe it: zoom in and pan — the number of rendered POIs/lines should drop and responses should stay snappy.

### LOD (zoom-aware) performance

On top of AOI slicing, the backend applies **zoom-aware level-of-detail (LOD)** to keep the map responsive when zoomed out:

- **Beer POIs**: clustered into aggregated markers at low zoom (trace name `Beer POIs (clusters)`)
- **Lines + polygons**: simplified as zoom decreases to reduce vertex counts
- **Payload budgets**: hard caps ensure we don't ship huge Plotly traces

### Optional: DuckDB engine (GeoParquet)

The backend supports an optional **DuckDB/GeoParquet** engine. Select via `PANGE_ENGINE=in_memory|duckdb` (some scenarios may require DuckDB).

### Data sources

See `data/prague/README.md` for provenance + download links.

## How to run

### Backend

```bash
cd backend/
```

Then follow [How to run](./backend/README.md#how-to-run) in backend folder

### Frontend

```bash
cd frontend/
```

Then follow [How to run](./frontend/README.md#how-to-run) in frontend folder
