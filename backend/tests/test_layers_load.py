from layers.load_prague import load_prague_layers


def test_load_prague_layers_non_empty():
    layers = load_prague_layers()
    assert len(layers.beer_pois) > 0
    assert len(layers.metro_ways) > 0
    assert len(layers.flood_q100) > 0

