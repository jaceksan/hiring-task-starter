from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb
from shapely.wkb import loads as wkb_loads

from engine.duckdb_common import duckdb_threads
from geo.aoi import BBox
from layers.types import Layer, LayerBundle, LineFeature, PointFeature, PolygonFeature
from scenarios.registry import get_scenario, resolve_repo_path


def _geoparquet_cache_decimals() -> int:
    raw = (os.getenv("PANGE_GEOPARQUET_AOI_DECIMALS") or "").strip()
    if raw:
        try:
            return max(2, min(6, int(raw)))
        except Exception:
            pass
    return 3


def _default_geom_min_zoom() -> float:
    raw = (os.getenv("PANGE_GEOPARQUET_GEOM_MIN_ZOOM") or "").strip()
    if raw:
        try:
            return float(raw)
        except Exception:
            pass
    return 11.0


@lru_cache(maxsize=128)
def _geoparquet_bundle_cached(
    scenario_id: str,
    *,
    aoi_key: tuple[float, float, float, float],
    zoom_bucket: int,
) -> LayerBundle:
    scenario = get_scenario(scenario_id).config
    aoi = BBox(
        min_lon=aoi_key[0], min_lat=aoi_key[1], max_lon=aoi_key[2], max_lat=aoi_key[3]
    )
    view_zoom = float(zoom_bucket) / 2.0

    conn = duckdb.connect(
        database=":memory:", read_only=False, config={"threads": int(duckdb_threads())}
    )
    try:
        out_layers: list[Layer] = []
        for l in scenario.layers:
            if l.source.type != "geoparquet":
                out_layers.append(
                    Layer(
                        id=l.id,
                        kind=l.kind,
                        title=l.title,
                        features=[],
                        style=l.style or {},
                    )
                )
                continue
            p = resolve_repo_path(l.source.path)
            out_layers.append(
                _query_geoparquet_layer_bbox(
                    conn,
                    layer_id=l.id,
                    kind=l.kind,
                    title=l.title,
                    style=l.style or {},
                    path=p,
                    aoi=aoi,
                    view_zoom=view_zoom,
                    source_options=l.source.geoparquet or None,
                )
            )
        return LayerBundle(layers=out_layers)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def query_geoparquet_layers_cached(
    scenario_id: str, *, aoi: BBox, view_zoom: float
) -> LayerBundle:
    decimals = _geoparquet_cache_decimals()
    aoi_key = aoi.rounded_key(decimals)
    zoom_bucket = int(round(float(view_zoom) * 2.0))
    return _geoparquet_bundle_cached(
        scenario_id, aoi_key=aoi_key, zoom_bucket=zoom_bucket
    )


@lru_cache(maxsize=64)
def _geoparquet_bbox_exprs(path: Path) -> dict[str, str]:
    # Detect bbox encoding.
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


def _query_geoparquet_layer_bbox(
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
) -> Layer:
    b = aoi.normalized()
    bbox = _geoparquet_bbox_exprs(path)
    where = f"{bbox['xmax']} >= ? AND {bbox['xmin']} <= ? AND {bbox['ymax']} >= ? AND {bbox['ymin']} <= ?"
    params = (b.min_lon, b.max_lon, b.min_lat, b.max_lat)

    # Safety caps
    if view_zoom <= 7.5:
        limit = 50_000 if kind == "points" else (20_000 if kind == "lines" else 10_000)
    elif view_zoom <= 9.0:
        limit = 150_000 if kind == "points" else (60_000 if kind == "lines" else 30_000)
    else:
        limit = (
            500_000 if kind == "points" else (200_000 if kind == "lines" else 100_000)
        )

    opts = source_options or {}
    id_col = str(opts.get("idColumn") or "osm_id")
    name_col = opts.get("nameColumn")
    class_col = opts.get("classColumn")
    geom_col = str(opts.get("geometryColumn") or "geometry")
    geom_min_zoom = float(opts.get("minZoomForGeometry") or _default_geom_min_zoom())

    name_expr = f"CAST({name_col} AS VARCHAR) AS name" if name_col else "NULL AS name"
    class_expr = (
        f"CAST({class_col} AS VARCHAR) AS fclass" if class_col else "NULL AS fclass"
    )

    if kind == "points":
        rows = conn.execute(
            f"""
            SELECT CAST({id_col} AS VARCHAR) AS id,
                   CAST({bbox["xmin"]} AS DOUBLE) AS lon,
                   CAST({bbox["ymin"]} AS DOUBLE) AS lat,
                   {name_expr},
                   {class_expr}
              FROM read_parquet(?)
             WHERE {where}
             LIMIT {int(limit)}
            """,
            [str(path), *params],
        ).fetchall()
        feats: list[PointFeature] = []
        for fid, lon, lat, name, fclass in rows:
            props: dict[str, Any] = {}
            if name:
                props["name"] = str(name)
                props["label"] = str(name)
            if fclass:
                props["fclass"] = str(fclass)
            feats.append(
                PointFeature(id=str(fid), lon=float(lon), lat=float(lat), props=props)
            )
        return Layer(
            id=layer_id, kind="points", title=title, features=feats, style=style or {}
        )

    # Lines/Polygons: decode geometry
    if float(view_zoom) < geom_min_zoom:
        return Layer(
            id=layer_id, kind=kind, title=title, features=[], style=style or {}
        )

    rows = conn.execute(
        f"""
        SELECT CAST({id_col} AS VARCHAR) AS id,
               CAST({geom_col} AS BLOB) AS geom_wkb,
               {name_expr},
               {class_expr}
          FROM read_parquet(?)
         WHERE {where}
         LIMIT {int(limit)}
        """,
        [str(path), *params],
    ).fetchall()

    if kind == "lines":
        feats: list[LineFeature] = []
        for fid, geom_wkb, name, fclass in rows:
            try:
                geom = wkb_loads(bytes(geom_wkb)) if geom_wkb is not None else None
            except Exception:
                geom = None
            if geom is None:
                continue
            props: dict[str, Any] = {}
            if name:
                props["name"] = str(name)
            if fclass:
                props["fclass"] = str(fclass)
            if geom.geom_type == "LineString":
                coords = [(float(x), float(y)) for x, y in geom.coords]
                if len(coords) >= 2:
                    feats.append(LineFeature(id=str(fid), coords=coords, props=props))
            elif geom.geom_type == "MultiLineString":
                for i, part in enumerate(getattr(geom, "geoms", []) or []):
                    coords = [(float(x), float(y)) for x, y in part.coords]
                    if len(coords) >= 2:
                        feats.append(
                            LineFeature(id=f"{fid}:{i}", coords=coords, props=props)
                        )
        return Layer(
            id=layer_id, kind="lines", title=title, features=feats, style=style or {}
        )

    feats2: list[PolygonFeature] = []

    def _poly_to_feature(pid: str, poly, props: dict[str, Any]) -> None:
        try:
            ext = [(float(x), float(y)) for x, y in poly.exterior.coords]
        except Exception:
            return
        if len(ext) < 4:
            return
        feats2.append(PolygonFeature(id=pid, rings=[ext], props=props))

    for fid, geom_wkb, name, fclass in rows:
        try:
            geom = wkb_loads(bytes(geom_wkb)) if geom_wkb is not None else None
        except Exception:
            geom = None
        if geom is None:
            continue
        props: dict[str, Any] = {}
        if name:
            props["name"] = str(name)
        if fclass:
            props["fclass"] = str(fclass)
        if geom.geom_type == "Polygon":
            _poly_to_feature(str(fid), geom, props)
        elif geom.geom_type == "MultiPolygon":
            for i, part in enumerate(getattr(geom, "geoms", []) or []):
                _poly_to_feature(f"{fid}:{i}", part, props)

    return Layer(
        id=layer_id, kind="polygons", title=title, features=feats2, style=style or {}
    )
