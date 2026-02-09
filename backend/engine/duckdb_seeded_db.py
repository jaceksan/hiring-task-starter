from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from geo.aoi import BBox
from layers.types import Layer, LayerBundle, LineFeature, PointFeature, PolygonFeature
from scenarios.registry import get_scenario


def connect(path: str, *, threads: int) -> duckdb.DuckDBPyConnection:
    p = Path(path)
    if p.parent and str(p.parent) not in {".", ""}:
        p.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(
        database=str(p), read_only=False, config={"threads": int(threads)}
    )


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS points (
          layer_id TEXT,
          id TEXT,
          lon DOUBLE,
          lat DOUBLE,
          props_json TEXT,
          min_lon DOUBLE,
          min_lat DOUBLE,
          max_lon DOUBLE,
          max_lat DOUBLE,
          PRIMARY KEY(layer_id, id)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lines (
          layer_id TEXT,
          id TEXT,
          coords_json TEXT,
          props_json TEXT,
          min_lon DOUBLE,
          min_lat DOUBLE,
          max_lon DOUBLE,
          max_lat DOUBLE,
          PRIMARY KEY(layer_id, id)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polygons (
          layer_id TEXT,
          id TEXT,
          rings_json TEXT,
          props_json TEXT,
          min_lon DOUBLE,
          min_lat DOUBLE,
          max_lon DOUBLE,
          max_lat DOUBLE,
          PRIMARY KEY(layer_id, id)
        );
        """
    )


def _count(conn: duckdb.DuckDBPyConnection, table: str) -> int:
    row = conn.execute("SELECT COUNT(*) FROM " + table).fetchone()
    return int(row[0] or 0) if row else 0


def _bbox_coords(
    coords: list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return float(min(lons)), float(min(lats)), float(max(lons)), float(max(lats))


def _bbox_rings(
    rings: list[list[tuple[float, float]]],
) -> tuple[float, float, float, float]:
    lons: list[float] = []
    lats: list[float] = []
    for r in rings:
        for lon, lat in r:
            lons.append(lon)
            lats.append(lat)
    if not lons or not lats:
        return 0.0, 0.0, 0.0, 0.0
    return float(min(lons)), float(min(lats)), float(max(lons)), float(max(lats))


def seed_all_layers(conn: duckdb.DuckDBPyConnection, layers: LayerBundle) -> None:
    # Seed only if empty (per DB file).
    if _count(conn, "points") == 0:
        point_rows = []
        for layer in layers.of_kind("points"):
            for f in layer.features:
                if not isinstance(f, PointFeature):
                    continue
                props = json.dumps(f.props or {}, ensure_ascii=False)
                point_rows.append(
                    (
                        layer.id,
                        f.id,
                        f.lon,
                        f.lat,
                        props,
                        f.lon,
                        f.lat,
                        f.lon,
                        f.lat,
                    )
                )
        conn.executemany(
            "INSERT OR IGNORE INTO points VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            point_rows,
        )

    if _count(conn, "lines") == 0:
        line_rows = []
        for layer in layers.of_kind("lines"):
            for f in layer.features:
                if not isinstance(f, LineFeature):
                    continue
                min_lon, min_lat, max_lon, max_lat = _bbox_coords(f.coords)
                line_rows.append(
                    (
                        layer.id,
                        f.id,
                        json.dumps(f.coords),
                        json.dumps(f.props or {}, ensure_ascii=False),
                        min_lon,
                        min_lat,
                        max_lon,
                        max_lat,
                    )
                )
        conn.executemany(
            "INSERT OR IGNORE INTO lines VALUES (?, ?, ?, ?, ?, ?, ?, ?)", line_rows
        )

    if _count(conn, "polygons") == 0:
        poly_rows = []
        for layer in layers.of_kind("polygons"):
            for f in layer.features:
                if not isinstance(f, PolygonFeature):
                    continue
                min_lon, min_lat, max_lon, max_lat = _bbox_rings(f.rings)
                poly_rows.append(
                    (
                        layer.id,
                        f.id,
                        json.dumps(f.rings),
                        json.dumps(f.props or {}, ensure_ascii=False),
                        min_lon,
                        min_lat,
                        max_lon,
                        max_lat,
                    )
                )
        conn.executemany(
            "INSERT OR IGNORE INTO polygons VALUES (?, ?, ?, ?, ?, ?, ?, ?)", poly_rows
        )


def query_seeded_layers_bbox(
    conn: duckdb.DuckDBPyConnection, aoi: BBox, *, scenario_id: str
) -> LayerBundle:
    b = aoi.normalized()
    params = (b.min_lon, b.max_lon, b.min_lat, b.max_lat)
    where = "max_lon >= ? AND min_lon <= ? AND max_lat >= ? AND min_lat <= ?"

    scenario = get_scenario(scenario_id).config
    out: list[Layer] = []

    rows = conn.execute(
        f"SELECT layer_id, id, lon, lat, props_json FROM points WHERE {where}",
        params,
    ).fetchall()
    by_layer: dict[str, list[PointFeature]] = {}
    for layer_id, fid, lon, lat, props_json in rows:
        by_layer.setdefault(str(layer_id), []).append(
            PointFeature(
                id=str(fid),
                lon=float(lon),
                lat=float(lat),
                props=json.loads(props_json or "{}"),
            )
        )

    rows = conn.execute(
        f"SELECT layer_id, id, coords_json, props_json FROM lines WHERE {where}",
        params,
    ).fetchall()
    by_layer_lines: dict[str, list[LineFeature]] = {}
    for layer_id, fid, coords_json, props_json in rows:
        coords = [
            (float(lon), float(lat)) for lon, lat in json.loads(coords_json or "[]")
        ]
        by_layer_lines.setdefault(str(layer_id), []).append(
            LineFeature(
                id=str(fid), coords=coords, props=json.loads(props_json or "{}")
            )
        )

    rows = conn.execute(
        f"SELECT layer_id, id, rings_json, props_json FROM polygons WHERE {where}",
        params,
    ).fetchall()
    by_layer_polys: dict[str, list[PolygonFeature]] = {}
    for layer_id, fid, rings_json, props_json in rows:
        rings = [
            [(float(lon), float(lat)) for lon, lat in ring]
            for ring in json.loads(rings_json or "[]")
        ]
        by_layer_polys.setdefault(str(layer_id), []).append(
            PolygonFeature(
                id=str(fid), rings=rings, props=json.loads(props_json or "{}")
            )
        )

    for lcfg in scenario.layers:
        feats: list[Any] = []
        if lcfg.kind == "points":
            feats = by_layer.get(lcfg.id, [])
        elif lcfg.kind == "lines":
            feats = by_layer_lines.get(lcfg.id, [])
        elif lcfg.kind == "polygons":
            feats = by_layer_polys.get(lcfg.id, [])
        out.append(
            Layer(
                id=lcfg.id,
                kind=lcfg.kind,
                title=lcfg.title,
                features=sorted(feats, key=lambda f: f.id),
                style=lcfg.style or {},
            )
        )

    return LayerBundle(layers=out)
