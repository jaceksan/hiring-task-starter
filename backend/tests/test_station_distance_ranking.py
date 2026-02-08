from shapely.geometry import Polygon

from agent import router
from geo.ops import build_geo_index
from layers.types import PointFeature, PragueLayers


def test_rank_dry_by_metro_station_prefers_closer_pub():
    # Use Prague-ish coordinates so the EPSG:32633 projection is sensible.
    station = PointFeature(id="node/1", lon=14.4378, lat=50.0755, props={"label": "Station"})

    near = PointFeature(id="node/2", lon=14.4380, lat=50.0755, props={"label": "Near pub"})
    far = PointFeature(id="node/3", lon=14.4500, lat=50.0755, props={"label": "Far pub"})

    layers = PragueLayers(
        flood_q100=[],
        metro_ways=[],
        beer_pois=[near, far],
        metro_stations=[station],
        tram_ways=[],
        tram_stops=[],
    )
    index = build_geo_index(layers)

    ranked = router._rank_dry_by_metro_station(  # noqa: SLF001 (test a small, stable unit)
        layers.beer_pois,
        flood_union_4326=Polygon(),
        index=index,
        top_n=2,
    )

    assert [pt.id for pt, _ in ranked] == ["node/2", "node/3"]

