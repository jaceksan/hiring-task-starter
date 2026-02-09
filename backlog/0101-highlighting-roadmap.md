## Highlighting roadmap

### Outcome (completed)

- Never silently render an incomplete highlight:
  - chat messages explicitly note when highlight rules are clipped by `maxFeatures`
  - `/invoke` always emits a note when rendered highlights are fewer than requested (including 0)
- LOD now preserves highlighted points even when the highlighted layer is an auxiliary points layer capped by budgets.
- Commit: `d4e5a0e`

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

