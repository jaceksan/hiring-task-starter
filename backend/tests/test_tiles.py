from __future__ import annotations

from geo.aoi import BBox
from geo.ops import build_geo_index
from geo.tiles import lonlat_to_tile, tile_bbox_4326, tiles_for_bbox
from layers.types import LineFeature, PolygonFeature, PragueLayers


def test_tiles_for_bbox_is_stable_within_same_tile():
    z = 12
    # Pick a stable Prague-ish coordinate.
    lon = 14.4378
    lat = 50.0755

    x, y = lonlat_to_tile(z, lon, lat)
    tb = tile_bbox_4326(z, x, y)

    # Two tiny AOIs fully inside the same tile should map to the same single tile.
    a0 = BBox(
        min_lon=lon - 0.0005,
        min_lat=lat - 0.0005,
        max_lon=lon + 0.0005,
        max_lat=lat + 0.0005,
    )
    a1 = BBox(
        min_lon=lon - 0.0007,
        min_lat=lat - 0.0002,
        max_lon=lon + 0.0002,
        max_lat=lat + 0.0007,
    )
    assert tiles_for_bbox(z, a0) == [(z, x, y)]
    assert tiles_for_bbox(z, a1) == [(z, x, y)]
    # Sanity: ensure the tile bbox actually contains our point.
    assert tb.min_lon <= lon <= tb.max_lon
    assert tb.min_lat <= lat <= tb.max_lat


def test_slice_layers_tiled_dedupes_cross_tile_features():
    z = 12
    # Use Prague-ish location to get a tile; then craft geometries crossing the east boundary.
    base_lon = 14.4378
    base_lat = 50.0755
    x, y = lonlat_to_tile(z, base_lon, base_lat)
    tb = tile_bbox_4326(z, x, y)
    boundary_lon = tb.max_lon
    mid_lat = (tb.min_lat + tb.max_lat) / 2.0

    # Line crossing the tile boundary -> it will be selected by both tile bbox queries.
    line = LineFeature(
        id="line-cross",
        coords=[(boundary_lon - 0.0001, mid_lat), (boundary_lon + 0.0001, mid_lat)],
        props={},
    )

    # Polygon crossing boundary as a thin rectangle.
    ring = [
        (boundary_lon - 0.00015, mid_lat - 0.00005),
        (boundary_lon + 0.00015, mid_lat - 0.00005),
        (boundary_lon + 0.00015, mid_lat + 0.00005),
        (boundary_lon - 0.00015, mid_lat + 0.00005),
        (boundary_lon - 0.00015, mid_lat - 0.00005),
    ]
    poly = PolygonFeature(id="poly-cross", rings=[ring], props={})

    layers = PragueLayers(flood_q100=[poly], metro_ways=[line], beer_pois=[])
    index = build_geo_index(layers)

    # AOI covering both tiles horizontally.
    tb2 = tile_bbox_4326(z, x + 1, y)
    aoi = BBox(
        min_lon=tb.min_lon,
        min_lat=tb.min_lat,
        max_lon=tb2.max_lon,
        max_lat=tb.max_lat,
    ).normalized()

    sliced = index.slice_layers_tiled(aoi, tile_zoom=z)
    assert [f.id for f in sliced.metro_ways] == ["line-cross"]
    assert [f.id for f in sliced.flood_q100] == ["poly-cross"]

