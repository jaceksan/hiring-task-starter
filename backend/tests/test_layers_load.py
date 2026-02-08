from layers.load_scenario import load_scenario_layers


def test_load_prague_transport_non_empty():
    bundle = load_scenario_layers("prague_transport")
    assert bundle.get("beer_pois") is not None
    assert bundle.get("metro_ways") is not None
    assert bundle.get("metro_stations") is not None
    assert bundle.get("tram_ways") is not None
    assert bundle.get("tram_stops") is not None
    assert bundle.get("flood_q100") is not None

    assert len(bundle.get("beer_pois").features) > 0
    assert len(bundle.get("metro_ways").features) > 0
    assert len(bundle.get("metro_stations").features) > 0
    assert len(bundle.get("tram_ways").features) > 0
    assert len(bundle.get("tram_stops").features) > 0
    assert len(bundle.get("flood_q100").features) > 0

