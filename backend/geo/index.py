from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from pyproj import Transformer
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.geometry import box as shapely_box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from geo.aoi import BBox
from geo.tile_bbox import tile_bbox_as_tuple
from geo.tiles import tiles_for_bbox
from layers.types import (
    GeometryKind,
    Layer,
    LayerBundle,
    LineFeature,
    PointFeature,
    PolygonFeature,
)


@dataclass
class GeoIndex:
    """
    Generic geometry index for a `LayerBundle`.

    Notes:
    - Input data is EPSG:4326 (lon/lat degrees).
    - Distance computations are done in EPSG:3857 (approx meters; good enough for MVP).
    """

    layers: LayerBundle

    # Per-layer STRtree indexes for bbox slicing (EPSG:4326)
    _layer_tree: dict[str, STRtree] = field(default_factory=dict, repr=False)
    _layer_geoms: dict[str, list[Any]] = field(default_factory=dict, repr=False)
    _layer_feats: dict[str, list[Any]] = field(default_factory=dict, repr=False)
    _layer_kind: dict[str, GeometryKind] = field(default_factory=dict, repr=False)

    # Per-point-layer projected indexes (EPSG:3857)
    _point_tree_3857: dict[str, STRtree] = field(default_factory=dict, repr=False)
    _point_geoms_3857: dict[str, list[Point]] = field(default_factory=dict, repr=False)

    # Caches
    _slice_cache: dict[tuple[str, tuple[float, float, float, float]], LayerBundle] = (
        field(default_factory=dict, repr=False)
    )
    _poly_union_cache: dict[
        tuple[str, tuple[float, float, float, float]], Polygon | MultiPolygon
    ] = field(default_factory=dict, repr=False)
    _tile_slice_cache: dict[tuple[int, int, int], LayerBundle] = field(
        default_factory=dict, repr=False
    )

    def slice_layers_tiled(
        self, aoi: BBox, *, tile_zoom: int, decimals: int = 4
    ) -> LayerBundle:
        tiles = tiles_for_bbox(tile_zoom, aoi)
        if not tiles:
            return LayerBundle(
                layers=[
                    Layer(
                        id=layer.id,
                        kind=layer.kind,
                        title=layer.title,
                        features=[],
                        style=layer.style,
                    )
                    for layer in self.layers.layers
                ]
            )

        tiles = sorted(tiles, key=lambda t: (t[1], t[2]))

        # Merge by (layer_id, feature_id) to dedupe across tiles.
        by_layer: dict[str, dict[str, Any]] = {
            layer.id: {} for layer in self.layers.layers
        }

        for z, x, y in tiles:
            key = (int(z), int(x), int(y))
            cached = self._tile_slice_cache.get(key)
            if cached is None:
                tb = BBox(*tile_bbox_as_tuple(z, x, y))  # type: ignore[arg-type]
                cached = self.slice_layers(tb, decimals=decimals)
                _bounded_cache_put(self._tile_slice_cache, key, cached, max_items=256)

            for layer in cached.layers:
                bucket = by_layer.get(layer.id)
                if bucket is None:
                    bucket = {}
                    by_layer[layer.id] = bucket
                for f in layer.features:
                    fid = getattr(f, "id", None)
                    if fid is None:
                        continue
                    bucket.setdefault(str(fid), f)

        out_layers: list[Layer] = []
        for base in self.layers.layers:
            feats = by_layer.get(base.id, {})
            ordered = [feats[k] for k in sorted(feats.keys())]
            out_layers.append(
                Layer(
                    id=base.id,
                    kind=base.kind,
                    title=base.title,
                    features=ordered,
                    style=base.style,
                )
            )
        return LayerBundle(layers=out_layers)

    def slice_layers(self, aoi: BBox, *, decimals: int = 4) -> LayerBundle:
        key = aoi.rounded_key(decimals)
        # Cache key is per-layer-set id; we use a synthetic id derived from layer ids.
        lid_key = ",".join([layer.id for layer in self.layers.layers])
        ck = (lid_key, key)
        cached = self._slice_cache.get(ck)
        if cached is not None:
            return cached

        bbox = shapely_box(aoi.min_lon, aoi.min_lat, aoi.max_lon, aoi.max_lat)
        out_layers: list[Layer] = []
        for layer in self.layers.layers:
            tree = self._layer_tree.get(layer.id)
            feats = self._layer_feats.get(layer.id) or []
            if tree is None:
                out_layers.append(
                    Layer(
                        id=layer.id,
                        kind=layer.kind,
                        title=layer.title,
                        features=[],
                        style=layer.style,
                    )
                )
                continue
            idxs = _to_int_list(tree.query(bbox))
            sliced = [feats[i] for i in idxs] if idxs else []
            out_layers.append(
                Layer(
                    id=layer.id,
                    kind=layer.kind,
                    title=layer.title,
                    features=sliced,
                    style=layer.style,
                )
            )

        out = LayerBundle(layers=out_layers)
        _bounded_cache_put(self._slice_cache, ck, out, max_items=64)
        return out

    def polygon_union_for_aoi(
        self, layer_id: str, aoi: BBox, *, decimals: int = 4
    ) -> Polygon | MultiPolygon:
        key = aoi.rounded_key(decimals)
        ck = (layer_id, key)
        cached = self._poly_union_cache.get(ck)
        if cached is not None:
            return cached

        layer = self.layers.get(layer_id)
        if layer is None or layer.kind != "polygons":
            u: Polygon | MultiPolygon = Polygon()
            _bounded_cache_put(self._poly_union_cache, ck, u, max_items=64)
            return u

        bbox = shapely_box(aoi.min_lon, aoi.min_lat, aoi.max_lon, aoi.max_lat)
        tree = self._layer_tree.get(layer_id)
        geoms = self._layer_geoms.get(layer_id) or []
        if tree is None:
            u = Polygon()
            _bounded_cache_put(self._poly_union_cache, ck, u, max_items=64)
            return u

        idxs = _to_int_list(tree.query(bbox))
        polys = [geoms[i] for i in idxs] if idxs else []
        if not polys:
            u = Polygon()
        else:
            u = unary_union(polys)
            if hasattr(u, "buffer"):
                u = u.buffer(0)
        _bounded_cache_put(self._poly_union_cache, ck, u, max_items=64)
        return u

    def distance_to_nearest_point_m(
        self, point: PointFeature, *, point_layer_id: str
    ) -> float:
        """
        Distance from `point` to nearest point in `point_layer_id` (meters, approx).
        """
        tree = self._point_tree_3857.get(point_layer_id)
        pts = self._point_geoms_3857.get(point_layer_id)
        if tree is None or pts is None or not pts:
            return float("inf")

        x, y = transformer_4326_to_3857().transform(point.lon, point.lat)
        q = Point(float(x), float(y))
        nearest_idx = tree.nearest(q)
        try:
            idx = int(nearest_idx)  # type: ignore[arg-type]
        except Exception:
            return float("inf")
        if idx < 0 or idx >= len(pts):
            return float("inf")
        return float(q.distance(pts[idx]))


@lru_cache(maxsize=1)
def transformer_4326_to_3857() -> Transformer:
    return Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)


def build_geo_index(bundle: LayerBundle) -> GeoIndex:
    idx = GeoIndex(layers=bundle)
    for layer in bundle.layers:
        kind = layer.kind
        idx._layer_kind[layer.id] = kind
        feats = layer.features
        idx._layer_feats[layer.id] = feats

        if kind == "points":
            geoms = [
                Point(float(getattr(f, "lon")), float(getattr(f, "lat"))) for f in feats
            ]  # type: ignore[arg-type]
            idx._layer_geoms[layer.id] = geoms
            idx._layer_tree[layer.id] = STRtree(geoms) if geoms else STRtree([])

            # projected tree
            pts_3857: list[Point] = []
            for f in feats:  # type: ignore[assignment]
                if not isinstance(f, PointFeature):
                    continue
                x, y = transformer_4326_to_3857().transform(f.lon, f.lat)
                pts_3857.append(Point(float(x), float(y)))
            idx._point_geoms_3857[layer.id] = pts_3857
            idx._point_tree_3857[layer.id] = (
                STRtree(pts_3857) if pts_3857 else STRtree([])
            )

        elif kind == "lines":
            geoms = []
            for f in feats:
                if not isinstance(f, LineFeature):
                    continue
                if len(f.coords) < 2:
                    continue
                geoms.append(
                    LineString([(float(lon), float(lat)) for lon, lat in f.coords])
                )
            idx._layer_geoms[layer.id] = geoms
            idx._layer_tree[layer.id] = STRtree(geoms) if geoms else STRtree([])

        elif kind == "polygons":
            geoms = []
            for f in feats:
                if not isinstance(f, PolygonFeature):
                    continue
                if not f.rings:
                    continue
                ring = f.rings[0]
                if not ring:
                    continue
                geoms.append(Polygon([(float(lon), float(lat)) for lon, lat in ring]))
            idx._layer_geoms[layer.id] = geoms
            idx._layer_tree[layer.id] = STRtree(geoms) if geoms else STRtree([])

    return idx


def is_point_in_union(point: PointFeature, union_poly: Polygon | MultiPolygon) -> bool:
    try:
        return bool(union_poly.contains(Point(point.lon, point.lat)))
    except Exception:
        return False


def _to_int_list(idxs: Any) -> list[int]:
    if idxs is None:
        return []
    try:
        return [int(i) for i in idxs]
    except Exception:
        try:
            return [int(i) for i in list(idxs)]
        except Exception:
            return []


def _bounded_cache_put(cache: dict, key, value, *, max_items: int) -> None:
    cache[key] = value
    if len(cache) > max_items:
        try:
            oldest = next(iter(cache.keys()))
            if oldest != key:
                cache.pop(oldest, None)
        except Exception:
            pass
