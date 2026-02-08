from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable

from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon
from shapely.geometry import box as shapely_box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from geo.aoi import BBox
from layers.types import LineFeature, PointFeature, PolygonFeature, PragueLayers


@dataclass
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

    # AOI slicing indexes (all in EPSG:4326 for bbox filtering)
    flood_tree_4326: STRtree
    flood_geoms_4326: list[Polygon]
    flood_features: list[PolygonFeature]

    metro_tree_4326: STRtree
    metro_geoms_4326: list[LineString]
    metro_features: list[LineFeature]

    beer_tree_4326: STRtree
    beer_geoms_4326: list[Point]
    beer_features: list[PointFeature]

    # Caches keyed by a rounded bbox
    _slice_cache: dict[tuple[float, float, float, float], PragueLayers] = field(
        default_factory=dict, repr=False
    )
    _flood_union_cache: dict[tuple[float, float, float, float], Polygon | MultiPolygon] = field(
        default_factory=dict, repr=False
    )

    def slice_layers(self, aoi: BBox, *, decimals: int = 4) -> PragueLayers:
        """
        Slice all three layers to AOI using STRtrees (fast bbox selection).

        This is intentionally approximate: bbox selection is a good first cut and keeps the
        map payload small. We can add stricter predicates later if needed.
        """
        key = aoi.rounded_key(decimals)
        cached = self._slice_cache.get(key)
        if cached is not None:
            return cached

        bbox = _bbox_polygon(aoi)

        flood_idx = _to_int_list(self.flood_tree_4326.query(bbox))
        metro_idx = _to_int_list(self.metro_tree_4326.query(bbox))
        beer_idx = _to_int_list(self.beer_tree_4326.query(bbox))

        sliced = PragueLayers(
            flood_q100=[self.flood_features[i] for i in flood_idx],
            metro_ways=[self.metro_features[i] for i in metro_idx],
            beer_pois=[self.beer_features[i] for i in beer_idx],
        )

        _bounded_cache_put(self._slice_cache, key, sliced, max_items=64)
        return sliced

    def flood_union_for_aoi(self, aoi: BBox, *, decimals: int = 4) -> Polygon | MultiPolygon:
        """
        Build (and cache) a flood polygon union only for polygons intersecting AOI.
        """
        key = aoi.rounded_key(decimals)
        cached = self._flood_union_cache.get(key)
        if cached is not None:
            return cached

        bbox = _bbox_polygon(aoi)
        idxs = _to_int_list(self.flood_tree_4326.query(bbox))
        polys = [self.flood_geoms_4326[i] for i in idxs] if idxs else []
        if not polys:
            u: Polygon | MultiPolygon = Polygon()
        else:
            u = unary_union(polys)
            if hasattr(u, "buffer"):
                u = u.buffer(0)

        _bounded_cache_put(self._flood_union_cache, key, u, max_items=64)
        return u


@lru_cache(maxsize=1)
def transformer_4326_to_32633() -> Transformer:
    # Prague fits well into UTM zone 33N.
    return Transformer.from_crs("EPSG:4326", "EPSG:32633", always_xy=True)


def build_geo_index(
    layers: PragueLayers,
) -> GeoIndex:
    flood_polys_4326, flood_features = _build_flood_geoms_and_features_4326(
        layers.flood_q100
    )
    flood_union = _union_polygons(flood_polys_4326)

    metro_lines_4326, metro_features = _build_metro_geoms_and_features_4326(
        layers.metro_ways
    )
    metro_union_32633 = _build_metro_union_32633(layers.metro_ways)

    beer_points_4326 = [Point(p.lon, p.lat) for p in layers.beer_pois]

    return GeoIndex(
        flood_union_4326=flood_union,
        metro_union_32633=metro_union_32633,
        flood_tree_4326=STRtree(flood_polys_4326),
        flood_geoms_4326=flood_polys_4326,
        flood_features=flood_features,
        metro_tree_4326=STRtree(metro_lines_4326),
        metro_geoms_4326=metro_lines_4326,
        metro_features=metro_features,
        beer_tree_4326=STRtree(beer_points_4326),
        beer_geoms_4326=beer_points_4326,
        beer_features=list(layers.beer_pois),
    )


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


def _build_flood_geoms_and_features_4326(
    polygons: Iterable[PolygonFeature],
) -> tuple[list[Polygon], list[PolygonFeature]]:
    shapely_polys: list[Polygon] = []
    out_features: list[PolygonFeature] = []
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
            out_features.append(f)
        except Exception:
            continue

    return shapely_polys, out_features


def _union_polygons(polys: list[Polygon]) -> Polygon | MultiPolygon:
    if not polys:
        return Polygon()
    u = unary_union(polys)
    # unary_union may yield GeometryCollection; force to polygon-ish via buffer(0)
    if hasattr(u, "buffer"):
        u = u.buffer(0)
    return u  # type: ignore[return-value]


def _build_metro_geoms_and_features_4326(
    lines: Iterable[LineFeature],
) -> tuple[list[LineString], list[LineFeature]]:
    shapely_lines: list[LineString] = []
    out_features: list[LineFeature] = []
    for f in lines:
        if len(f.coords) < 2:
            continue
        try:
            ls = LineString(f.coords)
            if ls.is_empty:
                continue
            shapely_lines.append(ls)
            out_features.append(f)
        except Exception:
            continue
    return shapely_lines, out_features


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


def _bbox_polygon(aoi: BBox) -> Polygon:
    b = aoi.normalized()
    return shapely_box(b.min_lon, b.min_lat, b.max_lon, b.max_lat)


def _to_int_list(arr) -> list[int]:
    # Shapely STRtree returns numpy.ndarray of indices.
    try:
        return [int(x) for x in arr.tolist()]
    except Exception:
        return [int(x) for x in arr]


def _bounded_cache_put(cache: dict, key, value, *, max_items: int) -> None:
    cache[key] = value
    # Simple bounded cache: remove oldest inserted key when we exceed size.
    if len(cache) > max_items:
        try:
            oldest = next(iter(cache.keys()))
            if oldest != key:
                cache.pop(oldest, None)
        except Exception:
            pass

