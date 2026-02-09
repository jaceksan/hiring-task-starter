from __future__ import annotations

from typing import Any

import duckdb


def query_points_rows(
    conn: duckdb.DuckDBPyConnection,
    *,
    path: str,
    where_sql: str,
    where_params: tuple[float, float, float, float],
    id_col: str,
    xmin_expr: str,
    ymin_expr: str,
    name_expr: str,
    class_expr: str,
    limit: int,
) -> list[tuple]:
    return conn.execute(
        f"""
        SELECT CAST({id_col} AS VARCHAR) AS id,
               CAST({xmin_expr} AS DOUBLE) AS lon,
               CAST({ymin_expr} AS DOUBLE) AS lat,
               {name_expr},
               {class_expr}
          FROM read_parquet(?)
         WHERE {where_sql}
         LIMIT {int(limit)}
        """,
        [str(path), *where_params],
    ).fetchall()


def query_points_rows_sampled(
    conn: duckdb.DuckDBPyConnection,
    *,
    path: str,
    where_sql: str,
    where_params: tuple[float, float, float, float],
    id_col: str,
    xmin_expr: str,
    ymin_expr: str,
    name_col: str | None,
    class_col: str | None,
    limit: int,
) -> list[tuple]:
    """
    Sample points *after* applying the AOI filter.

    Why:
      A plain LIMIT can return a spatially biased “slice” of the Parquet file (whatever comes
      first), which looks like a bug on the initial wide-AOI view. Sampling yields a more
      representative overview without requiring expensive global ORDER BY.
    """
    name_raw = str(name_col) if name_col else "NULL"
    class_raw = str(class_col) if class_col else "NULL"
    name_expr = "CAST(name_raw AS VARCHAR) AS name" if name_col else "NULL AS name"
    class_expr = (
        "CAST(class_raw AS VARCHAR) AS fclass" if class_col else "NULL AS fclass"
    )

    return conn.execute(
        f"""
        SELECT CAST(id_raw AS VARCHAR) AS id,
               CAST(lon_raw AS DOUBLE) AS lon,
               CAST(lat_raw AS DOUBLE) AS lat,
               {name_expr},
               {class_expr}
          FROM (
                SELECT {id_col} AS id_raw,
                       {xmin_expr} AS lon_raw,
                       {ymin_expr} AS lat_raw,
                       {name_raw} AS name_raw,
                       {class_raw} AS class_raw
                  FROM read_parquet(?)
                 WHERE {where_sql}
               )
         USING SAMPLE {int(limit)} ROWS
        """,
        [str(path), *where_params],
    ).fetchall()


def query_geometry_rows_no_policy(
    conn: duckdb.DuckDBPyConnection,
    *,
    path: str,
    where_sql: str,
    where_params: tuple[float, float, float, float],
    id_col: str,
    geom_col: str,
    name_expr: str,
    class_expr: str,
    limit: int,
) -> list[tuple]:
    return conn.execute(
        f"""
        SELECT CAST({id_col} AS VARCHAR) AS id,
               CAST({geom_col} AS BLOB) AS geom_wkb,
               {name_expr},
               {class_expr}
          FROM read_parquet(?)
         WHERE {where_sql}
         LIMIT {int(limit)}
        """,
        [str(path), *where_params],
    ).fetchall()


def query_candidate_ids(
    conn: duckdb.DuckDBPyConnection,
    *,
    path: str,
    where_sql: str,
    where_params: tuple[float, float, float, float],
    id_col: str,
    class_col: str | None,
    allow_classes: set[str] | None,
    name_expr: str,
    class_expr: str,
    order_by_sql: str | None,
    limit: int,
) -> list[str]:
    class_filter_sql = ""
    params: list[Any] = [str(path), *where_params]
    if allow_classes and class_col:
        class_filter_sql = f" AND CAST({class_col} AS VARCHAR) = ANY(?)"
        params.append(sorted(allow_classes))

    order_by_clause = ""
    if isinstance(order_by_sql, str) and order_by_sql.strip():
        order_by_clause = f" ORDER BY {order_by_sql.strip()}"

    rows = conn.execute(
        f"""
        SELECT CAST({id_col} AS VARCHAR) AS id,
               {name_expr},
               {class_expr}
          FROM read_parquet(?)
         WHERE {where_sql}{class_filter_sql}
         {order_by_clause}
         LIMIT {int(limit)}
        """,
        params,
    ).fetchall()
    return [str(r[0]) for r in rows if r and r[0]]


def query_geometry_rows_for_ids(
    conn: duckdb.DuckDBPyConnection,
    *,
    path: str,
    where_sql: str,
    where_params: tuple[float, float, float, float],
    id_col: str,
    geom_col: str,
    name_expr: str,
    class_expr: str,
    ids: list[str],
    limit: int,
) -> list[tuple]:
    return conn.execute(
        f"""
        SELECT CAST({id_col} AS VARCHAR) AS id,
               CAST({geom_col} AS BLOB) AS geom_wkb,
               {name_expr},
               {class_expr}
          FROM read_parquet(?)
         WHERE {where_sql}
           AND CAST({id_col} AS VARCHAR) = ANY(?)
         LIMIT {int(limit)}
        """,
        [str(path), *where_params, ids],
    ).fetchall()
