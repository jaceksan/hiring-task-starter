## GeoArrow evaluation

Reference: [GeoArrow](https://geoarrow.org/)

### Why consider it

GeoArrow standardizes storing geometries in Arrow-compatible structures, potentially enabling:

- lower overhead geometry transport/interop vs WKB-heavy pipelines
- easier integration with Arrow ecosystem tooling (including Parquet readers/writers)

### Smallest useful experiment

- Pick one expensive layer (roads or water).
- Try an Arrow-native path for “query → decode → serialize to frontend” (even if frontend still needs GeoJSON-ish).
- Measure `decodeMs` + `jsonSerialize` impact and compare with current WKB decode path.

