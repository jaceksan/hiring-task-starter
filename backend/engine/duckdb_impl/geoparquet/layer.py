from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import duckdb

from engine.duckdb_impl.geoparquet.bbox import geoparquet_bbox_exprs
from engine.duckdb_impl.geoparquet.config import (
    class_expr,
    default_geom_min_zoom,
    name_expr,
    parse_columns,
    safety_limit,
)
from engine.duckdb_impl.geoparquet.decode import (
    decode_line_rows,
    decode_polygon_rows,
)
from engine.duckdb_impl.geoparquet.points import query_geoparquet_points_layer_bbox
from engine.duckdb_impl.geoparquet.policy import (
    allowed_classes,
    choose_by_max_zoom,
    order_by,
)
from engine.duckdb_impl.geoparquet.sql import (
    query_candidate_ids,
    query_geometry_rows_for_ids,
    query_geometry_rows_no_policy,
)
from engine.duckdb_impl.geoparquet.stats import base_stats
from geo.aoi import BBox
from layers.types import Layer


def query_geoparquet_layer_bbox(
    conn: duckdb.DuckDBPyConnection,
    *,
    layer_id: str,
    kind: str,
    title: str,
    style: dict[str, Any],
    path: Path,
    aoi: BBox,
    view_zoom: float,
    source_options: dict[str, Any] | None,
) -> tuple[Layer, dict[str, Any]]:
    """
    Query a single GeoParquet layer for an AOI.

    Returns:
      - Layer with decoded features (subject to caps/policy)
      - Stats dict for telemetry/HUD
    """
    t0 = time.perf_counter()
    b = aoi.normalized()
    bbox = geoparquet_bbox_exprs(path)
    where_sql = f"{bbox['xmax']} >= ? AND {bbox['xmin']} <= ? AND {bbox['ymax']} >= ? AND {bbox['ymin']} <= ?"
    where_params = (b.min_lon, b.max_lon, b.min_lat, b.max_lat)

    safety = int(safety_limit(kind=kind, view_zoom=float(view_zoom)))
    opts = source_options or {}
    cols = parse_columns(opts)
    geom_min_zoom = float(opts.get("minZoomForGeometry") or default_geom_min_zoom())

    policy = (
        opts.get("renderPolicy") if isinstance(opts.get("renderPolicy"), dict) else None
    )
    allow = allowed_classes(policy, float(view_zoom))
    order_by_sql = order_by(policy, bbox=bbox)
    max_candidates = choose_by_max_zoom(
        (policy or {}).get("maxCandidatesByZoom") if isinstance(policy, dict) else None,
        float(view_zoom),
        default=None,
    )

    n_expr = name_expr(cols.name_col)
    c_expr = class_expr(cols.class_col)

    if kind == "points":
        return query_geoparquet_points_layer_bbox(
            conn,
            layer_id=layer_id,
            title=title,
            style=style or {},
            path=path,
            aoi=aoi,
            view_zoom=view_zoom,
            source_options=source_options,
        )

    # Lines/polygons: decode geometry (optionally with a zoom+class “overview” policy).
    # Default behavior (no renderPolicy): no decoding below minZoomForGeometry.
    if float(view_zoom) < geom_min_zoom and not allow:
        layer = Layer(
            id=layer_id, kind=kind, title=title, features=[], style=style or {}
        )
        return layer, base_stats(
            layer_id=layer_id,
            kind=kind,
            view_zoom=float(view_zoom),
            n=0,
            duckdb_ms=0.0,
            decode_ms=0.0,
            total_ms=(time.perf_counter() - t0) * 1000.0,
            skipped_reason="belowMinZoomForGeometry",
            geom_min_zoom=float(geom_min_zoom),
        )

    policy_enabled = policy is not None
    cand_limit = int(safety)
    max_candidates_int = int(max_candidates) if max_candidates is not None else None
    if max_candidates_int is not None:
        cand_limit = max(1, min(int(cand_limit), int(max_candidates_int)))

    # Hard caps to keep decoding/serialization stable on dense line/polygon layers.
    # LOD runs *after* decoding; without a pre-cap, we can spend seconds decoding
    # tens of thousands of WKB geometries only to drop most of them later.
    hard_cap = None
    if kind == "lines":
        # Lines (roads) are by far the densest layer; keep a strict cap to ensure
        # /plot refreshes remain interactive even on worst-case AOIs.
        hard_cap = 9_000
    elif kind == "polygons":
        hard_cap = 5_000
    if hard_cap is not None:
        cand_limit = max(1, min(int(cand_limit), int(hard_cap)))

    capped_by: list[str] = []
    # Note: safetyLimit is the initial upper bound; we report only tighter caps.
    if max_candidates_int is not None and max_candidates_int < safety:
        capped_by.append("policyMaxCandidates")
    if hard_cap is not None and hard_cap < min(safety, max_candidates_int or safety):
        capped_by.append("hardCap")

    cap_meta: dict[str, Any] = {
        "safetyLimit": int(safety),
        "policyMaxCandidates": max_candidates_int,
        "hardCap": int(hard_cap) if hard_cap is not None else None,
        "effectiveLimit": int(cand_limit),
        "cappedBy": capped_by,
    }

    t_db0 = time.perf_counter()
    if not policy_enabled:
        rows = query_geometry_rows_no_policy(
            conn,
            path=str(path),
            where_sql=where_sql,
            where_params=where_params,
            id_col=cols.id_col,
            geom_col=cols.geom_col,
            name_expr=n_expr,
            class_expr=c_expr,
            limit=cand_limit,
        )
        policy_meta = {
            "enabled": False,
            "allowedClasses": 0,
            "candLimit": int(cand_limit),
        }
    else:
        ids = query_candidate_ids(
            conn,
            path=str(path),
            where_sql=where_sql,
            where_params=where_params,
            id_col=cols.id_col,
            class_col=cols.class_col,
            allow_classes=allow,
            name_expr=n_expr,
            class_expr=c_expr,
            order_by_sql=order_by_sql,
            limit=cand_limit,
        )
        if not ids:
            layer = Layer(
                id=layer_id, kind=kind, title=title, features=[], style=style or {}
            )
            return layer, base_stats(
                layer_id=layer_id,
                kind=kind,
                view_zoom=float(view_zoom),
                n=0,
                duckdb_ms=0.0,
                decode_ms=0.0,
                total_ms=(time.perf_counter() - t0) * 1000.0,
                cap=cap_meta,
                policy={
                    "enabled": True,
                    "allowedClasses": len(allow or []),
                    "candLimit": int(cand_limit),
                },
            )
        rows = query_geometry_rows_for_ids(
            conn,
            path=str(path),
            where_sql=where_sql,
            where_params=where_params,
            id_col=cols.id_col,
            geom_col=cols.geom_col,
            name_expr=n_expr,
            class_expr=c_expr,
            ids=ids,
            limit=cand_limit,
        )
        policy_meta = {
            "enabled": True,
            "allowedClasses": len(allow or []),
            "candLimit": int(cand_limit),
        }
    t_db_ms = (time.perf_counter() - t_db0) * 1000.0

    t_dec0 = time.perf_counter()
    if kind == "lines":
        feats = decode_line_rows(rows)
        t_decode_ms = (time.perf_counter() - t_dec0) * 1000.0
        layer = Layer(
            id=layer_id, kind="lines", title=title, features=feats, style=style or {}
        )
        return layer, base_stats(
            layer_id=layer_id,
            kind="lines",
            view_zoom=float(view_zoom),
            n=len(feats),
            duckdb_ms=t_db_ms,
            decode_ms=t_decode_ms,
            total_ms=(time.perf_counter() - t0) * 1000.0,
            cap=cap_meta,
            policy=policy_meta,
        )

    feats2 = decode_polygon_rows(rows)
    t_decode_ms = (time.perf_counter() - t_dec0) * 1000.0
    layer = Layer(
        id=layer_id, kind="polygons", title=title, features=feats2, style=style or {}
    )
    return layer, base_stats(
        layer_id=layer_id,
        kind="polygons",
        view_zoom=float(view_zoom),
        n=len(feats2),
        duckdb_ms=t_db_ms,
        decode_ms=t_decode_ms,
        total_ms=(time.perf_counter() - t0) * 1000.0,
        cap=cap_meta,
        policy=policy_meta,
    )
