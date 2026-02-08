from geo.aoi import BBox
from geo.index import build_geo_index, is_point_in_union
from layers.types import Layer, LayerBundle, PointFeature, PolygonFeature


def test_point_in_polygon_returns_bool():
    poly = PolygonFeature(
        id="p",
        rings=[[(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)]],
        props={},
    )
    pt = PointFeature(id="x", lon=1.0, lat=1.0, props={})
    bundle = LayerBundle(
        layers=[
            Layer(
                id="polys", kind="polygons", title="Polys", features=[poly], style={}
            ),
            Layer(id="points", kind="points", title="Points", features=[pt], style={}),
        ]
    )
    index = build_geo_index(bundle)
    u = index.polygon_union_for_aoi(
        "polys", BBox(min_lon=-1, min_lat=-1, max_lon=3, max_lat=3)
    )
    inside = is_point_in_union(pt, u)
    assert isinstance(inside, bool)
    assert inside is True


def test_distance_to_nearest_point_is_non_negative_meters():
    pt = PointFeature(id="a", lon=0.0, lat=0.0, props={})
    near = PointFeature(id="b", lon=0.0001, lat=0.0001, props={})
    bundle = LayerBundle(
        layers=[
            Layer(
                id="targets", kind="points", title="Targets", features=[near], style={}
            ),
            Layer(
                id="sources", kind="points", title="Sources", features=[pt], style={}
            ),
        ]
    )
    index = build_geo_index(bundle)
    d = index.distance_to_nearest_point_m(pt, point_layer_id="targets")
    assert isinstance(d, float)
    assert d >= 0.0
    assert d < 50_000.0
