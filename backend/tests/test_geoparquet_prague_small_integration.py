from __future__ import annotations

import pytest

from engine.duckdb import DuckDBEngine
from engine.types import MapContext
from geo.aoi import BBox


@pytest.mark.integration
def test_duckdb_geoparquet_prague_small_decodes_some_geometries():
    # Small bbox near Prague city center to keep geometry decoding quick.
    aoi = BBox(min_lon=14.41, min_lat=50.07, max_lon=14.47, max_lat=50.10)
    ctx = MapContext(
        scenario_id="prague_population_infrastructure_small",
        aoi=aoi,
        view_center={"lat": 50.085, "lon": 14.44},
        view_zoom=12.0,
    )

    res = DuckDBEngine(path=":memory:").get(ctx)
    roads = res.layers.get("roads")
    water = res.layers.get("water_areas")
    assert roads is not None and roads.kind == "lines"
    assert water is not None and water.kind == "polygons"
    # At zoom 12.0 we are above minZoomForGeometry → expect at least some decoded geometry.
    assert len(roads.features) > 0
    assert len(water.features) > 0

