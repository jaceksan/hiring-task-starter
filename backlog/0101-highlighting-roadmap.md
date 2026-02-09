## Highlighting roadmap

### Status

In progress (do not mark completed until manually verified on the large CZ scenario).

### Key UX invariant

Never silently render an incomplete highlight when LOD/budgets are involved.

### Next steps

- Make highlight behavior **deterministic** under budgets:
  - larger (separate) budget for highlight overlays, or deterministic subsample
  - always message: “matched X, rendering Y due to budget”
- Support multiple highlight overlays (IDs preserved across plot refresh).
- Clarify highlight modes (question-triggered vs static toggles).
- Add follow-up demos:
  - “escape roads near highlighted places” (YAML-driven)
  - polygon “intensity” shading

### Expected behavior (agreed contract)

- **“highlight motorways”** highlights **motorway/trunk features within the current map view (AOI)**.
  - If none are in view, we should not highlight anything and should say so explicitly.
- **Persistence across zoom**:
  - If a motorway segment was highlighted and is still inside the new AOI after zooming out, it should **remain present and highlighted** even if the base roads layer is capped/simplified.
  - It’s fine if *non-highlight* roads disappear when zooming out (caps), but highlighted ones should be “pinned”.

### Demo use-cases (to make this meaningful)

- **Flooded places**:
  - User: “show flooded places” → points in flood mask become highlighted.
- **Escape roads**:
  - User: “show me escape roads for flooded places”
  - Expected: highlight only roads *closest to* flooded places; flooded places stay highlighted.
  - Prefer avoiding roads in flooded zones (if we have flood mask polygons that can filter lines).
- **Flooded roads**:
  - Investigation: can we derive “flooded roads” by intersecting roads with flood polygons and highlight them?
- **Flood risk visualization**:
  - Investigation: add/ingest flood-risk polygons with severity (10y/50y/100y) and visualize via shaded polygons (same hue, different opacity).

### Testing note (E2E is tricky)

- A full Playwright test against the large CZ GeoParquet data is likely flaky/slow.
- Prefer a **backend test** for “pin highlighted IDs under caps” + a small-data scenario smoke test; only add E2E once we have a stable UI contract.

