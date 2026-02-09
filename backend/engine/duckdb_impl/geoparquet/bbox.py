from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import duckdb


@lru_cache(maxsize=64)
def geoparquet_bbox_exprs(path: Path) -> dict[str, str]:
    """
    Return SQL expressions to access the covering bbox columns for a GeoParquet file.

    Supported encodings:
    - top-level columns: xmin/ymin/xmax/ymax
    - GeoParquet covering struct: geometry_bbox.{xmin,ymin,xmax,ymax}
    """
    conn = duckdb.connect(database=":memory:")
    try:
        cols = [
            str(r[0])
            for r in conn.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
            ).fetchall()
        ]
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if all(c in cols for c in ["xmin", "ymin", "xmax", "ymax"]):
        return {"xmin": "xmin", "ymin": "ymin", "xmax": "xmax", "ymax": "ymax"}
    if "geometry_bbox" in cols:
        return {
            "xmin": "geometry_bbox.xmin",
            "ymin": "geometry_bbox.ymin",
            "xmax": "geometry_bbox.xmax",
            "ymax": "geometry_bbox.ymax",
        }
    raise ValueError(
        f"GeoParquet missing covering bbox columns: {path}. "
        "Expected xmin/ymin/xmax/ymax or geometry_bbox(xmin,ymin,xmax,ymax)."
    )
