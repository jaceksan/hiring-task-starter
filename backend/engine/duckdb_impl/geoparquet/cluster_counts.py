from __future__ import annotations

from pathlib import Path

import duckdb
from pyproj import Transformer

from engine.duckdb_impl.geoparquet.bbox import geoparquet_bbox_exprs
from geo.aoi import BBox
from lod.points import ClusterMarker


def query_exact_density_bins(
    *,
    path: Path,
    aoi: BBox,
    grid_m: float,
    place_category_filter: set[str] | None = None,
    max_bins: int | None = None,
) -> list[ClusterMarker]:
    if place_category_filter is not None and len(place_category_filter) == 0:
        return []

    b = aoi.normalized()
    bbox = geoparquet_bbox_exprs(path)
    where_sql = f"{bbox['xmax']} >= ? AND {bbox['xmin']} <= ? AND {bbox['ymax']} >= ? AND {bbox['ymin']} <= ?"
    params: list[object] = [b.min_lon, b.max_lon, b.min_lat, b.max_lat]
    place_filter_sql = ""
    if place_category_filter:
        place_filter_sql = " AND CAST(place_category AS VARCHAR) = ANY(?)"
        params.append(sorted(place_category_filter))

    limit_sql = (
        f" LIMIT {int(max_bins)}" if isinstance(max_bins, int) and max_bins > 0 else ""
    )

    conn = duckdb.connect(database=":memory:", read_only=False)
    try:
        rows = conn.execute(
            f"""
            WITH pts AS (
              SELECT
                CAST({bbox["xmin"]} AS DOUBLE) AS lon,
                CAST({bbox["ymin"]} AS DOUBLE) AS lat
              FROM read_parquet(?)
              WHERE {where_sql}{place_filter_sql}
            ),
            projected AS (
              SELECT
                CAST(FLOOR(((lon * PI() / 180.0) * 6378137.0) / ?) AS BIGINT) AS cx,
                CAST(FLOOR((LN(TAN(PI() / 4.0 + (lat * PI() / 360.0))) * 6378137.0) / ?) AS BIGINT) AS cy
              FROM pts
              WHERE lat > -85.05112878 AND lat < 85.05112878
            )
            SELECT cx, cy, CAST(COUNT(*) AS BIGINT) AS n
            FROM projected
            GROUP BY cx, cy
            ORDER BY n DESC, cx ASC, cy ASC
            {limit_sql}
            """,
            [str(path), *params, float(grid_m), float(grid_m)],
        ).fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    t_inv = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    out: list[ClusterMarker] = []
    for cx, cy, n in rows:
        x_center = (float(cx) + 0.5) * float(grid_m)
        y_center = (float(cy) + 0.5) * float(grid_m)
        lon, lat = t_inv.transform(x_center, y_center)
        count = int(n or 0)
        out.append(
            ClusterMarker(
                lon=float(lon),
                lat=float(lat),
                count=count,
                cell_x=int(cx),
                cell_y=int(cy),
                exact_count=count,
                bin_size_m=float(grid_m),
            )
        )
    return out


def enrich_clusters_with_exact_counts(
    *,
    path: Path,
    aoi: BBox,
    clusters: list[ClusterMarker] | None,
    grid_m: float,
    place_category_filter: set[str] | None = None,
) -> list[ClusterMarker] | None:
    if not clusters:
        return clusters
    if place_category_filter is not None and len(place_category_filter) == 0:
        return [
            ClusterMarker(
                lon=c.lon,
                lat=c.lat,
                count=c.count,
                cell_x=c.cell_x,
                cell_y=c.cell_y,
                exact_count=0,
                bin_size_m=c.bin_size_m,
            )
            for c in clusters
        ]

    b = aoi.normalized()
    bbox = geoparquet_bbox_exprs(path)
    where_sql = f"{bbox['xmax']} >= ? AND {bbox['xmin']} <= ? AND {bbox['ymax']} >= ? AND {bbox['ymin']} <= ?"
    params: list[object] = [b.min_lon, b.max_lon, b.min_lat, b.max_lat]
    place_filter_sql = ""
    if place_category_filter:
        place_filter_sql = " AND CAST(place_category AS VARCHAR) = ANY(?)"
        params.append(sorted(place_category_filter))

    conn = duckdb.connect(database=":memory:", read_only=False)
    try:
        conn.execute(
            "CREATE TEMP TABLE _cluster_cells (cx BIGINT NOT NULL, cy BIGINT NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO _cluster_cells (cx, cy) VALUES (?, ?)",
            [(int(c.cell_x), int(c.cell_y)) for c in clusters],
        )
        rows = conn.execute(
            f"""
            WITH pts AS (
              SELECT
                CAST({bbox["xmin"]} AS DOUBLE) AS lon,
                CAST({bbox["ymin"]} AS DOUBLE) AS lat
              FROM read_parquet(?)
              WHERE {where_sql}{place_filter_sql}
            ),
            projected AS (
              SELECT
                CAST(FLOOR(((lon * PI() / 180.0) * 6378137.0) / ?) AS BIGINT) AS cx,
                CAST(FLOOR((LN(TAN(PI() / 4.0 + (lat * PI() / 360.0))) * 6378137.0) / ?) AS BIGINT) AS cy
              FROM pts
              WHERE lat > -85.05112878 AND lat < 85.05112878
            )
            SELECT c.cx, c.cy, CAST(COUNT(p.cx) AS BIGINT) AS n
            FROM _cluster_cells c
            LEFT JOIN projected p
              ON p.cx = c.cx AND p.cy = c.cy
            GROUP BY c.cx, c.cy
            """,
            [str(path), *params, float(grid_m), float(grid_m)],
        ).fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    exact_by_cell = {(int(cx), int(cy)): int(n or 0) for cx, cy, n in rows}
    return [
        ClusterMarker(
            lon=c.lon,
            lat=c.lat,
            count=c.count,
            cell_x=c.cell_x,
            cell_y=c.cell_y,
            exact_count=exact_by_cell.get((int(c.cell_x), int(c.cell_y)), 0),
            bin_size_m=c.bin_size_m,
        )
        for c in clusters
    ]
