from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb
from shapely.wkb import loads as wkb_loads

from engine.types import EngineResult, LayerEngine, MapContext
from geo.aoi import BBox
from geo.index import GeoIndex, build_geo_index
from geo.tiles import tile_bbox_4326, tile_zoom_for_view_zoom, tiles_for_bbox
from layers.load_scenario import load_scenario_layers
from layers.types import Layer, LayerBundle, LineFeature, PointFeature, PolygonFeature
from scenarios.registry import default_scenario_id, get_scenario, resolve_repo_path


class DuckDBEngine(LayerEngine):
    """
    DuckDB-backed engine.

    Two modes:
    - Seeded mode (small scenarios): load features into generic DuckDB tables once.
    - Query-on-read GeoParquet mode (large scenarios): read parquet per AOI directly.
    """

    def __init__(self, *, path: str | None = None):
        self.path = path or (os.getenv("PANGE_DUCKDB_PATH") or None)

    def get(self, ctx: MapContext) -> EngineResult:
        scenario = get_scenario(ctx.scenario_id).config
        has_geoparquet = any(l.source.type == "geoparquet" for l in scenario.layers)
        if has_geoparquet:
            layers = _query_geoparquet_layers_cached(
                scenario.id,
                aoi=ctx.aoi,
                view_zoom=ctx.view_zoom,
            )
            index = build_geo_index(layers)
            return EngineResult(layers=layers, index=index)

        base = _seeded_base(_duckdb_path_for_scenario(ctx.scenario_id, override_path=self.path), ctx.scenario_id)
        base.ensure_initialized()
        tile_zoom = tile_zoom_for_view_zoom(ctx.view_zoom)
        sliced = base.slice_layers_tiled(ctx.aoi, tile_zoom=tile_zoom)
        return EngineResult(layers=sliced, index=base.index)


@dataclass
class _SeededBase:
    scenario_id: str
    path: str
    index: GeoIndex
    layers: LayerBundle
    threads: int
    _init_lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _initialized: bool = field(default=False, repr=False)
    _local: threading.local = field(default_factory=threading.local, repr=False)

    def ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            conn = _connect(self.path, threads=self.threads)
            try:
                _init_schema(conn)
                _seed_all_layers(conn, self.layers)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            self._initialized = True

    def _conn(self) -> duckdb.DuckDBPyConnection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = _connect(self.path, threads=self.threads)
            self._local.conn = c
        return c

    def _tile_cache(self) -> dict[tuple[int, int, int], LayerBundle]:
        cache = getattr(self._local, "tile_slice_cache", None)
        if cache is None:
            cache = {}
            self._local.tile_slice_cache = cache
        return cache

    def slice_layers_tiled(self, aoi: BBox, *, tile_zoom: int) -> LayerBundle:
        tiles = tiles_for_bbox(tile_zoom, aoi)
        if not tiles:
            return LayerBundle(layers=[Layer(id=l.id, kind=l.kind, title=l.title, features=[], style=l.style) for l in self.layers.layers])
        tiles = sorted(tiles, key=lambda t: (t[1], t[2]))

        conn = self._conn()
        cache = self._tile_cache()

        merged: dict[str, dict[str, Any]] = {l.id: {} for l in self.layers.layers}
        for z, x, y in tiles:
            key = (int(z), int(x), int(y))
            cached = cache.get(key)
            if cached is None:
                tb = tile_bbox_4326(z, x, y)
                cached = _query_seeded_layers_bbox(conn, tb, scenario_id=self.scenario_id)
                _bounded_cache_put(cache, key, cached, max_items=256)
            for l in cached.layers:
                bucket = merged.get(l.id)
                if bucket is None:
                    bucket = {}
                    merged[l.id] = bucket
                for f in l.features:
                    bucket.setdefault(getattr(f, "id", ""), f)

        out_layers: list[Layer] = []
        for base in self.layers.layers:
            feats = merged.get(base.id, {})
            ordered = [feats[k] for k in sorted(feats.keys()) if k]
            out_layers.append(Layer(id=base.id, kind=base.kind, title=base.title, features=ordered, style=base.style))
        return LayerBundle(layers=out_layers)


@lru_cache(maxsize=8)
def _seeded_base(path: str, scenario_id: str) -> _SeededBase:
    layers = load_scenario_layers(scenario_id)
    index = build_geo_index(layers)
    threads = _duckdb_threads()
    return _SeededBase(scenario_id=scenario_id, path=path, index=index, layers=layers, threads=threads)


def _duckdb_path_for_scenario(scenario_id: str | None, *, override_path: str | None) -> str:
    if override_path:
        return override_path
    env_path = (os.getenv("PANGE_DUCKDB_PATH") or "").strip()
    if env_path:
        return env_path
    sid = (scenario_id or "").strip() or default_scenario_id()
    base_dir = (os.getenv("PANGE_DUCKDB_DIR") or "data/duckdb").strip() or "data/duckdb"
    return str(Path(base_dir) / f"{sid}.duckdb")


def _duckdb_threads() -> int:
    raw = (os.getenv("PANGE_DUCKDB_THREADS") or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except Exception:
            pass
    return max(1, int(os.cpu_count() or 1))


def _connect(path: str, *, threads: int) -> duckdb.DuckDBPyConnection:
    p = Path(path)
    if p.parent and str(p.parent) not in {".", ""}:
        p.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(database=str(p), read_only=False, config={"threads": int(threads)})


def _init_schema(conn: duckdb.DuckDBPyConnection) -> None:
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


def _count(conn: duckdb.DuckDBPyConnection, table: str, *, scenario_id: str) -> int:
    row = conn.execute("SELECT COUNT(*) FROM " + table).fetchone()
    return int(row[0] or 0) if row else 0


def _bbox_coords(coords: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return float(min(lons)), float(min(lats)), float(max(lons)), float(max(lats))


def _bbox_rings(rings: list[list[tuple[float, float]]]) -> tuple[float, float, float, float]:
    lons: list[float] = []
    lats: list[float] = []
    for r in rings:
        for lon, lat in r:
            lons.append(lon)
            lats.append(lat)
    if not lons or not lats:
        return 0.0, 0.0, 0.0, 0.0
    return float(min(lons)), float(min(lats)), float(max(lons)), float(max(lats))


def _seed_all_layers(conn: duckdb.DuckDBPyConnection, layers: LayerBundle) -> None:
    # Seed only if empty (per DB file).
    if _count(conn, "points", scenario_id="") == 0:
        point_rows = []
        for l in layers.of_kind("points"):
            for f in l.features:
                if not isinstance(f, PointFeature):
                    continue
                props = json.dumps(f.props or {}, ensure_ascii=False)
                point_rows.append((l.id, f.id, f.lon, f.lat, props, f.lon, f.lat, f.lon, f.lat))
        conn.executemany("INSERT OR IGNORE INTO points VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", point_rows)

    if _count(conn, "lines", scenario_id="") == 0:
        line_rows = []
        for l in layers.of_kind("lines"):
            for f in l.features:
                if not isinstance(f, LineFeature):
                    continue
                min_lon, min_lat, max_lon, max_lat = _bbox_coords(f.coords)
                line_rows.append(
                    (
                        l.id,
                        f.id,
                        json.dumps(f.coords),
                        json.dumps(f.props or {}, ensure_ascii=False),
                        min_lon,
                        min_lat,
                        max_lon,
                        max_lat,
                    )
                )
        conn.executemany("INSERT OR IGNORE INTO lines VALUES (?, ?, ?, ?, ?, ?, ?, ?)", line_rows)

    if _count(conn, "polygons", scenario_id="") == 0:
        poly_rows = []
        for l in layers.of_kind("polygons"):
            for f in l.features:
                if not isinstance(f, PolygonFeature):
                    continue
                min_lon, min_lat, max_lon, max_lat = _bbox_rings(f.rings)
                poly_rows.append(
                    (
                        l.id,
                        f.id,
                        json.dumps(f.rings),
                        json.dumps(f.props or {}, ensure_ascii=False),
                        min_lon,
                        min_lat,
                        max_lon,
                        max_lat,
                    )
                )
        conn.executemany("INSERT OR IGNORE INTO polygons VALUES (?, ?, ?, ?, ?, ?, ?, ?)", poly_rows)


def _query_seeded_layers_bbox(conn: duckdb.DuckDBPyConnection, aoi: BBox, *, scenario_id: str) -> LayerBundle:
    b = aoi.normalized()
    params = (b.min_lon, b.max_lon, b.min_lat, b.max_lat)
    where = "max_lon >= ? AND min_lon <= ? AND max_lat >= ? AND min_lat <= ?"

    scenario = get_scenario(scenario_id).config
    out: list[Layer] = []

    # Points
    rows = conn.execute(
        f"SELECT layer_id, id, lon, lat, props_json FROM points WHERE {where}",
        params,
    ).fetchall()
    by_layer: dict[str, list[PointFeature]] = {}
    for layer_id, fid, lon, lat, props_json in rows:
        by_layer.setdefault(str(layer_id), []).append(
            PointFeature(id=str(fid), lon=float(lon), lat=float(lat), props=json.loads(props_json or "{}"))
        )

    # Lines
    rows = conn.execute(
        f"SELECT layer_id, id, coords_json, props_json FROM lines WHERE {where}",
        params,
    ).fetchall()
    by_layer_lines: dict[str, list[LineFeature]] = {}
    for layer_id, fid, coords_json, props_json in rows:
        coords = [(float(lon), float(lat)) for lon, lat in json.loads(coords_json or "[]")]
        by_layer_lines.setdefault(str(layer_id), []).append(
            LineFeature(id=str(fid), coords=coords, props=json.loads(props_json or "{}"))
        )

    # Polygons
    rows = conn.execute(
        f"SELECT layer_id, id, rings_json, props_json FROM polygons WHERE {where}",
        params,
    ).fetchall()
    by_layer_polys: dict[str, list[PolygonFeature]] = {}
    for layer_id, fid, rings_json, props_json in rows:
        rings = [[(float(lon), float(lat)) for lon, lat in ring] for ring in json.loads(rings_json or "[]")]
        by_layer_polys.setdefault(str(layer_id), []).append(
            PolygonFeature(id=str(fid), rings=rings, props=json.loads(props_json or "{}"))
        )

    for lcfg in scenario.layers:
        feats: list[Any] = []
        if lcfg.kind == "points":
            feats = by_layer.get(lcfg.id, [])
        elif lcfg.kind == "lines":
            feats = by_layer_lines.get(lcfg.id, [])
        elif lcfg.kind == "polygons":
            feats = by_layer_polys.get(lcfg.id, [])
        out.append(Layer(id=lcfg.id, kind=lcfg.kind, title=lcfg.title, features=sorted(feats, key=lambda f: f.id), style=lcfg.style or {}))

    return LayerBundle(layers=out)


def _bounded_cache_put(cache: dict, key, value, *, max_items: int) -> None:
    cache[key] = value
    if len(cache) > max_items:
        try:
            oldest = next(iter(cache.keys()))
            if oldest != key:
                cache.pop(oldest, None)
        except Exception:
            pass


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
@lru_cache(maxsize=128)
def _geoparquet_bundle_cached(
    scenario_id: str,
    *,
    aoi_key: tuple[float, float, float, float],
    zoom_bucket: int,
) -> LayerBundle:
    scenario = get_scenario(scenario_id).config
    aoi = BBox(min_lon=aoi_key[0], min_lat=aoi_key[1], max_lon=aoi_key[2], max_lat=aoi_key[3])
    view_zoom = float(zoom_bucket) / 2.0

    conn = duckdb.connect(database=":memory:", read_only=False, config={"threads": int(_duckdb_threads())})
    try:
        out_layers: list[Layer] = []
        for l in scenario.layers:
            if l.source.type != "geoparquet":
                out_layers.append(Layer(id=l.id, kind=l.kind, title=l.title, features=[], style=l.style or {}))
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


def _query_geoparquet_layers_cached(scenario_id: str, *, aoi: BBox, view_zoom: float) -> LayerBundle:
    decimals = _geoparquet_cache_decimals()
    aoi_key = aoi.rounded_key(decimals)
    zoom_bucket = int(round(float(view_zoom) * 2.0))
    return _geoparquet_bundle_cached(scenario_id, aoi_key=aoi_key, zoom_bucket=zoom_bucket)


@lru_cache(maxsize=64)
def _geoparquet_bbox_exprs(path: Path) -> dict[str, str]:
    # Detect bbox encoding.
    conn = duckdb.connect(database=":memory:")
    try:
        cols = [str(r[0]) for r in conn.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()]
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
    where = (
        f"{bbox['xmax']} >= ? AND {bbox['xmin']} <= ? AND {bbox['ymax']} >= ? AND {bbox['ymin']} <= ?"
    )
    params = (b.min_lon, b.max_lon, b.min_lat, b.max_lat)

    # Safety caps
    if view_zoom <= 7.5:
        limit = 50_000 if kind == "points" else (20_000 if kind == "lines" else 10_000)
    elif view_zoom <= 9.0:
        limit = 150_000 if kind == "points" else (60_000 if kind == "lines" else 30_000)
    else:
        limit = 500_000 if kind == "points" else (200_000 if kind == "lines" else 100_000)

    opts = source_options or {}
    id_col = str(opts.get("idColumn") or "osm_id")
    name_col = opts.get("nameColumn")
    class_col = opts.get("classColumn")
    geom_col = str(opts.get("geometryColumn") or "geometry")
    geom_min_zoom = float(opts.get("minZoomForGeometry") or _default_geom_min_zoom())

    name_expr = f"CAST({name_col} AS VARCHAR) AS name" if name_col else "NULL AS name"
    class_expr = f"CAST({class_col} AS VARCHAR) AS fclass" if class_col else "NULL AS fclass"

    if kind == "points":
        rows = conn.execute(
            f"""
            SELECT CAST({id_col} AS VARCHAR) AS id,
                   CAST({bbox['xmin']} AS DOUBLE) AS lon,
                   CAST({bbox['ymin']} AS DOUBLE) AS lat,
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
            feats.append(PointFeature(id=str(fid), lon=float(lon), lat=float(lat), props=props))
        return Layer(id=layer_id, kind="points", title=title, features=feats, style=style or {})

    # Lines/Polygons: decode geometry
    if float(view_zoom) < geom_min_zoom:
        return Layer(id=layer_id, kind=kind, title=title, features=[], style=style or {})

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
                        feats.append(LineFeature(id=f"{fid}:{i}", coords=coords, props=props))
        return Layer(id=layer_id, kind="lines", title=title, features=feats, style=style or {})

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

    return Layer(id=layer_id, kind="polygons", title=title, features=feats2, style=style or {})


def _query_geoparquet_layers_tiled(*_args, **_kwargs) -> LayerBundle:
    """
    Deprecated: GeoParquet mode now queries per viewport bbox (not per tile),
    to avoid `tiles × layers` query explosions.
    """
    raise RuntimeError("GeoParquet tiling mode is disabled; use bbox mode instead.")

