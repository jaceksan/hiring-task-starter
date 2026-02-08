from geo.ops import build_geo_index, distance_to_metro_m, is_point_flooded
from layers.load_prague import load_prague_layers


def test_point_in_polygon_returns_bool():
    layers = load_prague_layers()
    index = build_geo_index(layers.flood_q100, layers.metro_ways)

    pt = layers.beer_pois[0]
    flooded = is_point_flooded(pt, index.flood_union_4326)
    assert isinstance(flooded, bool)


def test_distance_to_metro_is_non_negative_meters():
    layers = load_prague_layers()
    index = build_geo_index(layers.flood_q100, layers.metro_ways)

    pt = layers.beer_pois[0]
    d = distance_to_metro_m(pt, index.metro_union_32633)
    assert isinstance(d, float)
    assert d >= 0.0
    # sanity: within 200km of metro network for Prague-ish bbox
    assert d < 200_000.0

