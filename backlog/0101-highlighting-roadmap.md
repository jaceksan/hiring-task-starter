## Highlighting roadmap

### Status

In progress.

Current state:
- “How many places are flooded?” is now reasonably stable in the CZ scenario.
- Other supported questions still need validation and possible simplification.

### Key UX invariant

Never silently render an incomplete highlight when LOD/budgets are involved.

### Next steps

- Enumerate every currently supported question and run manual verification on CZ.
- For failing/weak questions:
  - either simplify/remove them from the supported set, or
  - update behavior/UX until they are deterministic and reliable.
- Keep highlight behavior deterministic under budgets and always communicate when rendering is capped.
- Keep map focus + highlight persistence consistent across refreshes for all supported questions.

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

