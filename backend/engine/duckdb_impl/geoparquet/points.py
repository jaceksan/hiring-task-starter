from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import duckdb

from engine.duckdb_impl.geoparquet.bbox import geoparquet_bbox_exprs
from engine.duckdb_impl.geoparquet.config import (
    class_expr,
    name_expr,
    parse_columns,
    safety_limit,
)
from engine.duckdb_impl.geoparquet.decode import decode_point_rows
from engine.duckdb_impl.geoparquet.policy import choose_by_max_zoom
from engine.duckdb_impl.geoparquet.sql import (
    query_points_rows,
    query_points_rows_sampled,
)
from engine.duckdb_impl.geoparquet.stats import base_stats
from geo.aoi import BBox
from layers.types import Layer


def query_geoparquet_points_layer_bbox(
    conn: duckdb.DuckDBPyConnection,
    *,
    layer_id: str,
    title: str,
    style: dict[str, Any],
    path: Path,
    aoi: BBox,
    view_zoom: float,
    source_options: dict[str, Any] | None,
) -> tuple[Layer, dict[str, Any]]:
    t0 = time.perf_counter()
    b = aoi.normalized()
    bbox = geoparquet_bbox_exprs(path)
    where_sql = f"{bbox['xmax']} >= ? AND {bbox['xmin']} <= ? AND {bbox['ymax']} >= ? AND {bbox['ymin']} <= ?"
    where_params = (b.min_lon, b.max_lon, b.min_lat, b.max_lat)

    safety = int(safety_limit(kind="points", view_zoom=float(view_zoom)))
    opts = source_options or {}
    cols = parse_columns(opts)

    policy = (
        opts.get("renderPolicy") if isinstance(opts.get("renderPolicy"), dict) else None
    )
    max_candidates = choose_by_max_zoom(
        (policy or {}).get("maxCandidatesByZoom") if isinstance(policy, dict) else None,
        float(view_zoom),
        default=None,
    )
    max_candidates_int = int(max_candidates) if max_candidates is not None else None

    cand_limit = int(safety)
    if max_candidates_int is not None:
        cand_limit = max(1, min(int(cand_limit), int(max_candidates_int)))

    span_lon = float(b.max_lon - b.min_lon)
    span_lat = float(b.max_lat - b.min_lat)
    use_sample = (
        max_candidates_int is not None
        and max_candidates_int < safety
        and max(span_lon, span_lat) > 1.0
    )
    cap_meta: dict[str, Any] = {
        "safetyLimit": int(safety),
        "policyMaxCandidates": max_candidates_int,
        "hardCap": None,
        "effectiveLimit": int(cand_limit),
        "cappedBy": ["policyMaxCandidates"]
        if (max_candidates_int is not None and max_candidates_int < safety)
        else [],
        "sampled": bool(use_sample),
    }

    n_expr = name_expr(cols.name_col)
    c_expr = class_expr(cols.class_col)

    t_db0 = time.perf_counter()
    rows = (
        query_points_rows_sampled(
            conn,
            path=str(path),
            where_sql=where_sql,
            where_params=where_params,
            id_col=cols.id_col,
            xmin_expr=bbox["xmin"],
            ymin_expr=bbox["ymin"],
            name_col=cols.name_col,
            class_col=cols.class_col,
            limit=cand_limit,
        )
        if use_sample
        else query_points_rows(
            conn,
            path=str(path),
            where_sql=where_sql,
            where_params=where_params,
            id_col=cols.id_col,
            xmin_expr=bbox["xmin"],
            ymin_expr=bbox["ymin"],
            name_expr=n_expr,
            class_expr=c_expr,
            limit=cand_limit,
        )
    )
    t_db_ms = (time.perf_counter() - t_db0) * 1000.0

    t_dec0 = time.perf_counter()
    feats = decode_point_rows(rows)
    t_decode_ms = (time.perf_counter() - t_dec0) * 1000.0

    layer = Layer(
        id=layer_id, kind="points", title=title, features=feats, style=style or {}
    )
    return layer, base_stats(
        layer_id=layer_id,
        kind="points",
        view_zoom=float(view_zoom),
        n=len(feats),
        duckdb_ms=t_db_ms,
        decode_ms=t_decode_ms,
        total_ms=(time.perf_counter() - t0) * 1000.0,
        cap=cap_meta,
    )
