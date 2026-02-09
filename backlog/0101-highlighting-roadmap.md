## Highlighting roadmap

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

