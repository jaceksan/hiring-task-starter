## Scenario A performance (GeoParquet + Plotly)

### Outcome (completed)

- Implemented a slow-refresh toast with bottleneck summaries (step + slowest layer) and improved telemetry readability.
- Tightened GeoParquet caps (roads/water/places) and added cap metadata to engine stats to make “incomplete but fast” explicit.
- Fixed low-zoom `places` first-render bias by sampling capped points after AOI filtering.
- Commits: `0cb8d5b`, `77684ed`, `cb801d2`, `95dd1be`

### What we can still do (without switching to MVT yet)

- **Manually validate the baseline**
  - test `czech_population_infrastructure_large` end-to-end and fix regressions quickly
- **Telemetry: make bottlenecks obvious**
  - backend: ensure `layout.meta.stats.timingsMs` is complete and stable
  - backend: include per-layer stats/timings in a shape the UI can summarize (slowest layer, duckdb vs decode)
  - frontend: display rounded/meaningful values (zoom, timings, payload) + bottleneck summary
- **UX: slow refresh toast**
  - show a toast when `/plot` refresh exceeds **250ms**
  - toast must be dismissible and auto-dismiss after **10s**
  - show at most **once per page load**
- **Reduce decoded geometry volume**
  - tighten `renderPolicy` caps further and make “drop” behavior deterministic + surfaced in chat/telemetry
  - increase zoom thresholds for low-importance road classes
- **Make decode cheaper**
  - simplify geometries before shipping to Plotly (server-side)
  - consider caching simplified geometries per (zoom bucket, AOI bucket)
- **Make candidate selection cheaper**
  - keep `ORDER BY` disabled unless it demonstrably helps quality
  - prefer early-exit friendly queries (small LIMIT, selective filters)
- **Measure the right thing**
  - rely on per-layer `duckdbMs` vs `decodeMs`, and `jsonSerialize`
  - aim to keep worst-case “absorb zoom” under a target budget for demo

