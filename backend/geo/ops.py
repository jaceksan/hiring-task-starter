from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from layers.types import LineFeature, PointFeature, PolygonFeature


@dataclass(frozen=True)
class GeoIndex:
    """
    Precomputed geometry index for fast repeated queries.

    Geospatial note:
    - Input data is in EPSG:4326 (lon/lat degrees).
    - We keep flood polygons in EPSG:4326 for point-in-polygon (fine at city scale).
    - We project metro + points to a meter-based CRS for distance computations.
    """

    flood_union_4326: Polygon | MultiPolygon
    metro_union_32633: LineString | MultiLineString


@lru_cache(maxsize=1)
def transformer_4326_to_32633() -> Transformer:
    # Prague fits well into UTM zone 33N.
    return Transformer.from_crs("EPSG:4326", "EPSG:32633", always_xy=True)


def build_geo_index(
    flood_polygons: Iterable[PolygonFeature],
    metro_lines: Iterable[LineFeature],
) -> GeoIndex:
    flood_union = _build_flood_union_4326(flood_polygons)
    metro_union = _build_metro_union_32633(metro_lines)
    return GeoIndex(flood_union_4326=flood_union, metro_union_32633=metro_union)


def is_point_flooded(point: PointFeature, flood_union_4326: Polygon | MultiPolygon) -> bool:
    # covers() includes boundary points as flooded
    return flood_union_4326.covers(Point(point.lon, point.lat))


def distance_to_metro_m(
    point: PointFeature,
    metro_union_32633: LineString | MultiLineString,
) -> float:
    """
    Distance in meters from point to nearest metro line.

    Why projection matters:
    lon/lat are degrees, not meters. Projecting to UTM gives distances in meters,
    which makes sorting/ranking meaningful.
    """
    t = transformer_4326_to_32633()
    x, y = t.transform(point.lon, point.lat)
    return float(metro_union_32633.distance(Point(x, y)))


def _build_flood_union_4326(polygons: Iterable[PolygonFeature]) -> Polygon | MultiPolygon:
    shapely_polys: list[Polygon] = []
    for f in polygons:
        if not f.rings:
            continue
        outer = _ensure_closed(f.rings[0])
        if len(outer) < 4:
            continue
        holes = [_ensure_closed(r) for r in f.rings[1:] if len(r) >= 4]
        try:
            poly = Polygon(outer, holes=holes if holes else None)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                continue
            shapely_polys.append(poly)
        except Exception:
            continue

    if not shapely_polys:
        # Fallback: empty polygon
        return Polygon()

    u = unary_union(shapely_polys)
    # unary_union may yield GeometryCollection; force to polygon-ish via buffer(0)
    if hasattr(u, "buffer"):
        u = u.buffer(0)
    return u  # type: ignore[return-value]


def _build_metro_union_32633(lines: Iterable[LineFeature]) -> LineString | MultiLineString:
    t = transformer_4326_to_32633()
    shapely_lines: list[LineString] = []
    for f in lines:
        if len(f.coords) < 2:
            continue
        xs: list[float] = []
        ys: list[float] = []
        for lon, lat in f.coords:
            x, y = t.transform(lon, lat)
            xs.append(x)
            ys.append(y)
        coords = list(zip(xs, ys))
        try:
            ls = LineString(coords)
            if ls.is_empty:
                continue
            shapely_lines.append(ls)
        except Exception:
            continue

    if not shapely_lines:
        return LineString()

    u = unary_union(shapely_lines)
    return u  # type: ignore[return-value]


def _ensure_closed(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not ring:
        return ring
    if ring[0] != ring[-1]:
        return [*ring, ring[0]]
    return ring

