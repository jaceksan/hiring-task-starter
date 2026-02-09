## Scenario A performance (GeoParquet + Plotly)

### What we can still do (without switching to MVT yet)

- **Manually validate the baseline**
  - test `czech_population_infrastructure_large` end-to-end and fix regressions quickly
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

