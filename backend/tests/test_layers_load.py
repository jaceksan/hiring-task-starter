from layers.load_scenario import load_scenario_layers


def test_load_prague_transport_non_empty():
    bundle = load_scenario_layers("prague_transport")
    beer_pois = bundle.get("beer_pois")
    metro_ways = bundle.get("metro_ways")
    metro_stations = bundle.get("metro_stations")
    tram_ways = bundle.get("tram_ways")
    tram_stops = bundle.get("tram_stops")
    flood_q100 = bundle.get("flood_q100")

    assert beer_pois is not None
    assert metro_ways is not None
    assert metro_stations is not None
    assert tram_ways is not None
    assert tram_stops is not None
    assert flood_q100 is not None

    assert len(beer_pois.features) > 0
    assert len(metro_ways.features) > 0
    assert len(metro_stations.features) > 0
    assert len(tram_ways.features) > 0
    assert len(tram_stops.features) > 0
    assert len(flood_q100.features) > 0
