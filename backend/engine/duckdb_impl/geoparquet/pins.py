from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from engine.duckdb_impl.geoparquet.bbox import geoparquet_bbox_exprs
from engine.duckdb_impl.geoparquet.config import (
    class_expr,
    name_expr,
    parse_columns,
)
from engine.duckdb_impl.geoparquet.decode import (
    decode_line_rows,
    decode_point_rows,
    decode_polygon_rows,
)
from engine.duckdb_impl.geoparquet.sql import (
    query_geometry_rows_for_ids,
    query_points_rows_for_ids,
)
from geo.aoi import BBox
from layers.types import Layer


def query_geoparquet_layer_pinned_ids(
    conn: duckdb.DuckDBPyConnection,
    *,
    layer_id: str,
    kind: str,
    title: str,
    style: dict[str, Any],
    path: Path,
    aoi: BBox,
    view_zoom: float,  # reserved for future policy adjustments
    source_options: dict[str, Any] | None,
    ids: set[str],
) -> Layer:
    """
    Fetch a specific set of features by ID for the current AOI.

    Used to "pin" highlighted features into the layer bundle so they don't disappear when
    zooming out and the base layer is capped by candidate limits.
    """
    _ = float(view_zoom)  # keep signature stable; unused for now
    if not ids:
        return Layer(
            id=layer_id, kind=kind, title=title, features=[], style=style or {}
        )

    # Highlight IDs may include multipart suffixes (e.g. "osm_id:0"); query by base ID.
    base_ids = {str(x).split(":", 1)[0] for x in ids if x}
    if not base_ids:
        return Layer(
            id=layer_id, kind=kind, title=title, features=[], style=style or {}
        )

    b = aoi.normalized()
    bbox = geoparquet_bbox_exprs(path)
    where_sql = f"{bbox['xmax']} >= ? AND {bbox['xmin']} <= ? AND {bbox['ymax']} >= ? AND {bbox['ymin']} <= ?"
    where_params = (b.min_lon, b.max_lon, b.min_lat, b.max_lat)

    opts = source_options or {}
    cols = parse_columns(opts)
    n_expr = name_expr(cols.name_col)
    c_expr = class_expr(cols.class_col)

    base_list = sorted(base_ids)
    limit = max(1, len(base_list))

    if kind == "points":
        rows = query_points_rows_for_ids(
            conn,
            path=str(path),
            where_sql=where_sql,
            where_params=where_params,
            id_col=cols.id_col,
            xmin_expr=bbox["xmin"],
            ymin_expr=bbox["ymin"],
            name_expr=n_expr,
            class_expr=c_expr,
            ids=base_list,
            limit=limit,
        )
        feats = decode_point_rows(rows)
        return Layer(
            id=layer_id, kind="points", title=title, features=feats, style=style or {}
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
        ids=base_list,
        limit=limit,
    )
    if kind == "lines":
        feats2 = decode_line_rows(rows)
        return Layer(
            id=layer_id, kind="lines", title=title, features=feats2, style=style or {}
        )
    feats3 = decode_polygon_rows(rows)
    return Layer(
        id=layer_id, kind="polygons", title=title, features=feats3, style=style or {}
    )
