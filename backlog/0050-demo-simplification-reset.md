## Demo simplification reset

### Goal

Simplify the demo into one coherent story that is reliable, visually clear, and easy to explain.

### Scope (must-have)

- Keep only one layer set:
  - `places`
  - `flood_zones`
  - `roads`
- Keep only two scenarios:
  - small data: Prague
  - big data: whole Czech Republic
- For big CZ scenario, provide big datasets for all layers (not only roads).

### Data and visualization requirements

- Increase places coverage significantly compared to current state.
- Render flood zones as polygons with flood-risk-dependent shade intensity.
- Show metadata for all layers in UI interactions/tooltips/popups:
  - places: existing metadata + key useful fields
  - roads: key road metadata
  - flood_zones: at minimum related water entity naming (river/lake/etc.) where data allows

### Advanced demo use case (primary)

- Support: "show me escape roads for places in flood zone".
- This use case should be deterministic and demoable in both scenarios.

### Locked product decisions

- Active flood zone model: **hybrid**.
  - Default behavior: active zones are all flood zones intersecting current AOI.
  - Override behavior: if user selects one or more zones, selection wins over AOI default.
  - UI must always show which mode is active (`AOI (N)` vs `Selected (N)`).
- Flood-risk control: use **discrete levels** (not a free slider):
  - `High (100y)`
  - `Medium (50y+)`
  - `Any risk`
- Flood constraint UX baseline:
  - Keep AOI mode as zero-click default.
  - Provide optional zone selection + explicit risk level control.
  - Keep labels simple and demo-friendly.

### Multi-question demo requirement

- Demonstrate the system can answer more than one meaningful question.
- Keep implementation rule-based/non-LLM for now.
- Add one additional "catchy" supported question.
- **Locked second question**: "Show safest nearby places outside selected flood risk with reachable roads."

### Done criteria

- Demo works end-to-end for both scenarios with the simplified scope.
- Primary and secondary supported questions both execute reliably.
- UI clearly visualizes flood risk and metadata for all three layer types.
