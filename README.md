# Hiring task starter

This is a repo with React frontend and Python backend to get you started on your task.

## MVP implemented in this repo (Prague Flood & Beer)

This repo now contains an MVP that fulfills the core requirements from `requirements.pdf`:

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
