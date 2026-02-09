from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


def default_geom_min_zoom() -> float:
    raw = (os.getenv("PANGE_GEOPARQUET_GEOM_MIN_ZOOM") or "").strip()
    if raw:
        try:
            return float(raw)
        except Exception:
            pass
    return 11.0


def safety_limit(*, kind: str, view_zoom: float) -> int:
    z = float(view_zoom)
    if z <= 7.5:
        return 50_000 if kind == "points" else (20_000 if kind == "lines" else 10_000)
    if z <= 9.0:
        return 150_000 if kind == "points" else (60_000 if kind == "lines" else 30_000)
    return 500_000 if kind == "points" else (200_000 if kind == "lines" else 100_000)


@dataclass(frozen=True)
class LayerColumns:
    id_col: str
    name_col: str | None
    class_col: str | None
    geom_col: str


@dataclass(frozen=True)
class LayerPolicy:
    enabled: bool
    allow_classes: set[str] | None
    order_by_sql: str
    max_candidates: int | None


def parse_columns(opts: dict[str, Any]) -> LayerColumns:
    return LayerColumns(
        id_col=str(opts.get("idColumn") or "osm_id"),
        name_col=opts.get("nameColumn"),
        class_col=opts.get("classColumn"),
        geom_col=str(opts.get("geometryColumn") or "geometry"),
    )


def name_expr(name_col: str | None) -> str:
    return f"CAST({name_col} AS VARCHAR) AS name" if name_col else "NULL AS name"


def class_expr(class_col: str | None) -> str:
    return f"CAST({class_col} AS VARCHAR) AS fclass" if class_col else "NULL AS fclass"
