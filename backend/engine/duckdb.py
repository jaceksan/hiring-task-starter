from __future__ import annotations

from engine.types import EngineResult, LayerEngine, MapContext


class DuckDBEngine(LayerEngine):
    """
    Placeholder for a future DuckDB/GeoParquet-backed engine.

    Intended shape:
    - store normalized layers in (Geo)Parquet (or Parquet + WKB)
    - query by AOI (bbox + spatial predicate) and by zoom (LOD tables)
    - return the same EngineResult contract as InMemoryEngine
    """

    def __init__(self, *, path: str = "data/duckdb/pangeai.duckdb"):
        self.path = path

    def get(self, ctx: MapContext) -> EngineResult:
        raise NotImplementedError(
            "DuckDBEngine is not implemented yet. Use PANGE_ENGINE=in_memory."
        )

