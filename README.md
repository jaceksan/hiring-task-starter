# Hiring task starter

React + FastAPI geospatial demo app with chat-driven map analysis, multiple scenarios, and zoom-aware rendering.

## What is currently implemented

- **Frontend**: React + Plotly/Mapbox thread UI (`frontend/`)
- **Backend**: FastAPI streaming endpoint (`/invoke`) + map refresh endpoint (`/plot`) (`backend/`)
- **Scenarios**:
  - `prague_transport` (small, in-memory-friendly)
  - `prague_population_infrastructure_small` (GeoParquet/DuckDB)
  - `czech_population_infrastructure_large` (GeoParquet/DuckDB)
- **Performance model**: AOI-first querying + LOD/simplification + payload budgets + telemetry
- **Road highlighting UX** (CZ GeoParquet scenarios): map-side checkbox control for road types (`motorway`, `trunk`, `primary`, `secondary`, `tertiary`) with type-level all-or-none visibility in current viewport

## Quick start

From repo root:

```bash
make run-backend
```

In another terminal:

```bash
make run-frontend
```

Open `http://localhost:3000`.

## Useful commands

- `make fix-all`
- `make types-all`
- `make test-backend`
- `make test-e2e-frontend`

## Notes

- Engine can be selected in UI (`In-memory` / `DuckDB`); large scenario forces DuckDB.
- After changing scenario YAML/config, use **Reload config** in the UI (or `POST /dev/clear-caches`).

## More docs

- Product requirements: `requirements.pdf`
- Backend details: `backend/README.md`
- Frontend details: `frontend/README.md`
- Data provenance (Prague base layers): `data/prague/README.md`
- Current priorities: `BACKLOG.md`
