from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb

from engine.types import EngineResult, LayerEngine, MapContext
from geo.aoi import BBox
from geo.ops import build_geo_index
from geo.tiles import tile_bbox_4326, tile_zoom_for_view_zoom, tiles_for_bbox
from layers.load_prague import load_prague_layers
from layers.types import LineFeature, PointFeature, PolygonFeature, PragueLayers


class DuckDBEngine(LayerEngine):
    """
    DuckDB-backed engine (in-process) for AOI slicing.

    MVP intent:
    - load Prague layers into DuckDB tables at startup
    - query candidate features by bbox intersection (numeric min/max columns)
    - keep GeoIndex for spatial reasoning (flood union + metro distance) shared across engines

    This avoids the DuckDB spatial extension for now (works offline and keeps dependencies simple).
    """

    def __init__(self, *, path: str | None = None):
        # NOTE: For concurrency we need multiple connections. With DuckDB, separate connections
        # should connect to the same DB file. ":memory:" would create a per-connection DB, so we
        # use a file by default.
        self.path = path or (os.getenv("PANGE_DUCKDB_PATH") or "data/duckdb/prague.duckdb")

    def get(self, ctx: MapContext) -> EngineResult:
        base = _duckdb_base(self.path)
        base.ensure_initialized()

        # Use slippy tiles as stable cache keys while panning.
        tile_zoom = tile_zoom_for_view_zoom(ctx.view_zoom)
        layers = base.slice_layers_tiled(ctx.aoi, tile_zoom=tile_zoom)
        return EngineResult(layers=layers, index=base.index)


@dataclass
class _DuckDbBase:
    index: Any
    path: str
    threads: int
    _init_lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _initialized: bool = field(default=False, repr=False)
    _local: threading.local = field(default_factory=threading.local, repr=False)

    def ensure_initialized(self) -> None:
        """
        Initialize the database schema + seed data once.

        Concurrency note:
        DuckDB recommends *separate connections per thread*. We do that, but we still need
        a one-time initializer to create tables and seed them.
        """
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            conn = _connect(self.path, threads=self.threads)
            try:
                layers = load_prague_layers()
                _init_schema(conn)
                _load_layers(conn, layers)
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

    def _tile_cache(self) -> dict[tuple[int, int, int], PragueLayers]:
        cache = getattr(self._local, "tile_slice_cache", None)
        if cache is None:
            cache = {}
            self._local.tile_slice_cache = cache
        return cache

    def slice_layers_tiled(self, aoi: BBox, *, tile_zoom: int) -> PragueLayers:
        tiles = tiles_for_bbox(tile_zoom, aoi)
        if not tiles:
            return PragueLayers(flood_q100=[], metro_ways=[], beer_pois=[])

        tiles = sorted(tiles, key=lambda t: (t[1], t[2]))
        conn = self._conn()
        cache = self._tile_cache()

        flood_by_id: dict[str, PolygonFeature] = {}
        metro_by_id: dict[str, LineFeature] = {}
        metro_station_by_id: dict[str, PointFeature] = {}
        tram_by_id: dict[str, LineFeature] = {}
        tram_stop_by_id: dict[str, PointFeature] = {}
        beer_by_id: dict[str, PointFeature] = {}

        for z, x, y in tiles:
            key = (int(z), int(x), int(y))
            cached = cache.get(key)
            if cached is None:
                tb = tile_bbox_4326(z, x, y)
                cached = _query_layers_bbox(conn, tb)
                _bounded_cache_put(cache, key, cached, max_items=256)

            for f in cached.flood_q100:
                flood_by_id.setdefault(f.id, f)
            for f in cached.metro_ways:
                metro_by_id.setdefault(f.id, f)
            for f in cached.metro_stations:
                metro_station_by_id.setdefault(f.id, f)
            for f in cached.tram_ways:
                tram_by_id.setdefault(f.id, f)
            for f in cached.tram_stops:
                tram_stop_by_id.setdefault(f.id, f)
            for f in cached.beer_pois:
                beer_by_id.setdefault(f.id, f)

        flood = [flood_by_id[k] for k in sorted(flood_by_id.keys())]
        metro = [metro_by_id[k] for k in sorted(metro_by_id.keys())]
        metro_stations = [metro_station_by_id[k] for k in sorted(metro_station_by_id.keys())]
        tram = [tram_by_id[k] for k in sorted(tram_by_id.keys())]
        tram_stops = [tram_stop_by_id[k] for k in sorted(tram_stop_by_id.keys())]
        beer = [beer_by_id[k] for k in sorted(beer_by_id.keys())]
        return PragueLayers(
            flood_q100=flood,
            metro_ways=metro,
            metro_stations=metro_stations,
            tram_ways=tram,
            tram_stops=tram_stops,
            beer_pois=beer,
        )


@lru_cache(maxsize=2)
def _duckdb_base(path: str) -> _DuckDbBase:
    layers = load_prague_layers()
    index = build_geo_index(layers)
    threads = _duckdb_threads()
    return _DuckDbBase(index=index, path=path, threads=threads)


def _duckdb_threads() -> int:
    """
    Internal DuckDB query parallelism (NOT Python request concurrency).
    """
    raw = (os.getenv("PANGE_DUCKDB_THREADS") or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except Exception:
            pass
    # Default: use available cores. (User can tune via env.)
    return max(1, int(os.cpu_count() or 1))


def _connect(path: str, *, threads: int) -> duckdb.DuckDBPyConnection:
    # We keep write access because we seed tables once and cache may create WAL files.
    p = Path(path)
    if p.parent and str(p.parent) not in {".", ""}:
        p.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(database=str(p), read_only=False, config={"threads": int(threads)})


def _init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS beer_pois (
          id TEXT PRIMARY KEY,
          lon DOUBLE,
          lat DOUBLE,
          props_json TEXT,
          min_lon DOUBLE,
          min_lat DOUBLE,
          max_lon DOUBLE,
          max_lat DOUBLE
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metro_ways (
          id TEXT PRIMARY KEY,
          coords_json TEXT,
          props_json TEXT,
          min_lon DOUBLE,
          min_lat DOUBLE,
          max_lon DOUBLE,
          max_lat DOUBLE
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metro_stations (
          id TEXT PRIMARY KEY,
          lon DOUBLE,
          lat DOUBLE,
          props_json TEXT,
          min_lon DOUBLE,
          min_lat DOUBLE,
          max_lon DOUBLE,
          max_lat DOUBLE
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tram_ways (
          id TEXT PRIMARY KEY,
          coords_json TEXT,
          props_json TEXT,
          min_lon DOUBLE,
          min_lat DOUBLE,
          max_lon DOUBLE,
          max_lat DOUBLE
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tram_stops (
          id TEXT PRIMARY KEY,
          lon DOUBLE,
          lat DOUBLE,
          props_json TEXT,
          min_lon DOUBLE,
          min_lat DOUBLE,
          max_lon DOUBLE,
          max_lat DOUBLE
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS flood_q100 (
          id TEXT PRIMARY KEY,
          rings_json TEXT,
          props_json TEXT,
          min_lon DOUBLE,
          min_lat DOUBLE,
          max_lon DOUBLE,
          max_lat DOUBLE
        );
        """
    )


def _load_layers(conn: duckdb.DuckDBPyConnection, layers: PragueLayers) -> None:
    # Keep it idempotent: populate missing tables (supports upgrades of existing DB files).
    def _count(table: str) -> int:
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except Exception:
            return 0

    if _count("beer_pois") == 0:
        beer_rows = []
        for p in layers.beer_pois:
            beer_rows.append(
                (
                    p.id,
                    float(p.lon),
                    float(p.lat),
                    json.dumps(p.props, ensure_ascii=False),
                    float(p.lon),
                    float(p.lat),
                    float(p.lon),
                    float(p.lat),
                )
            )
        conn.executemany(
            "INSERT INTO beer_pois VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            beer_rows,
        )

    if _count("metro_ways") == 0:
        metro_rows = []
        for l in layers.metro_ways:
            min_lon, min_lat, max_lon, max_lat = _bbox_coords(l.coords)
            metro_rows.append(
                (
                    l.id,
                    json.dumps(l.coords),
                    json.dumps(l.props, ensure_ascii=False),
                    min_lon,
                    min_lat,
                    max_lon,
                    max_lat,
                )
            )
        conn.executemany(
            "INSERT INTO metro_ways VALUES (?, ?, ?, ?, ?, ?, ?)",
            metro_rows,
        )

    if _count("metro_stations") == 0:
        station_rows = []
        for p in layers.metro_stations:
            station_rows.append(
                (
                    p.id,
                    float(p.lon),
                    float(p.lat),
                    json.dumps(p.props, ensure_ascii=False),
                    float(p.lon),
                    float(p.lat),
                    float(p.lon),
                    float(p.lat),
                )
            )
        conn.executemany(
            "INSERT INTO metro_stations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            station_rows,
        )

    if _count("tram_ways") == 0:
        tram_rows = []
        for l in layers.tram_ways:
            min_lon, min_lat, max_lon, max_lat = _bbox_coords(l.coords)
            tram_rows.append(
                (
                    l.id,
                    json.dumps(l.coords),
                    json.dumps(l.props, ensure_ascii=False),
                    min_lon,
                    min_lat,
                    max_lon,
                    max_lat,
                )
            )
        conn.executemany(
            "INSERT INTO tram_ways VALUES (?, ?, ?, ?, ?, ?, ?)",
            tram_rows,
        )

    if _count("tram_stops") == 0:
        stop_rows = []
        for p in layers.tram_stops:
            stop_rows.append(
                (
                    p.id,
                    float(p.lon),
                    float(p.lat),
                    json.dumps(p.props, ensure_ascii=False),
                    float(p.lon),
                    float(p.lat),
                    float(p.lon),
                    float(p.lat),
                )
            )
        conn.executemany(
            "INSERT INTO tram_stops VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            stop_rows,
        )

    if _count("flood_q100") == 0:
        flood_rows = []
        for p in layers.flood_q100:
            min_lon, min_lat, max_lon, max_lat = _bbox_rings(p.rings)
            flood_rows.append(
                (
                    p.id,
                    json.dumps(p.rings),
                    json.dumps(p.props, ensure_ascii=False),
                    min_lon,
                    min_lat,
                    max_lon,
                    max_lat,
                )
            )
        conn.executemany(
            "INSERT INTO flood_q100 VALUES (?, ?, ?, ?, ?, ?, ?)",
            flood_rows,
        )


def _query_layers_bbox(conn: duckdb.DuckDBPyConnection, aoi: BBox) -> PragueLayers:
    b = aoi.normalized()
    params = (b.min_lon, b.max_lon, b.min_lat, b.max_lat)
    where = "max_lon >= ? AND min_lon <= ? AND max_lat >= ? AND min_lat <= ?"

    beers = conn.execute(
        f"SELECT id, lon, lat, props_json FROM beer_pois WHERE {where}",
        params,
    ).fetchall()
    beer_pois = [
        PointFeature(id=row[0], lon=float(row[1]), lat=float(row[2]), props=json.loads(row[3]))
        for row in beers
    ]

    metros = conn.execute(
        f"SELECT id, coords_json, props_json FROM metro_ways WHERE {where}",
        params,
    ).fetchall()
    metro_ways = [
        LineFeature(
            id=row[0],
            coords=[(float(lon), float(lat)) for lon, lat in json.loads(row[1])],
            props=json.loads(row[2]),
        )
        for row in metros
    ]

    stations = conn.execute(
        f"SELECT id, lon, lat, props_json FROM metro_stations WHERE {where}",
        params,
    ).fetchall()
    metro_stations = [
        PointFeature(id=row[0], lon=float(row[1]), lat=float(row[2]), props=json.loads(row[3]))
        for row in stations
    ]

    trams = conn.execute(
        f"SELECT id, coords_json, props_json FROM tram_ways WHERE {where}",
        params,
    ).fetchall()
    tram_ways = [
        LineFeature(
            id=row[0],
            coords=[(float(lon), float(lat)) for lon, lat in json.loads(row[1])],
            props=json.loads(row[2]),
        )
        for row in trams
    ]

    stops = conn.execute(
        f"SELECT id, lon, lat, props_json FROM tram_stops WHERE {where}",
        params,
    ).fetchall()
    tram_stops = [
        PointFeature(id=row[0], lon=float(row[1]), lat=float(row[2]), props=json.loads(row[3]))
        for row in stops
    ]

    floods = conn.execute(
        f"SELECT id, rings_json, props_json FROM flood_q100 WHERE {where}",
        params,
    ).fetchall()
    flood_q100 = [
        PolygonFeature(
            id=row[0],
            rings=[
                [(float(lon), float(lat)) for lon, lat in ring] for ring in json.loads(row[1])
            ],
            props=json.loads(row[2]),
        )
        for row in floods
    ]

    return PragueLayers(
        flood_q100=flood_q100,
        metro_ways=metro_ways,
        metro_stations=metro_stations,
        tram_ways=tram_ways,
        tram_stops=tram_stops,
        beer_pois=beer_pois,
    )


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


def _bounded_cache_put(cache: dict, key, value, *, max_items: int) -> None:
    cache[key] = value
    if len(cache) > max_items:
        try:
            oldest = next(iter(cache.keys()))
            if oldest != key:
                cache.pop(oldest, None)
        except Exception:
            pass

