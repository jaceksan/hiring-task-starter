from __future__ import annotations

from plotly.build_plot import Highlight, build_prague_plot
from layers.types import PointFeature, PragueLayers


def test_focus_map_does_not_zoom_out_aggressively():
    layers = PragueLayers(
        flood_q100=[],
        metro_ways=[],
        beer_pois=[
            PointFeature(id="a", lon=14.44, lat=50.08, props={}),
            PointFeature(id="b", lon=14.46, lat=50.09, props={}),
        ],
    )

    plot = build_prague_plot(
        layers,
        highlight=Highlight(point_ids={"a", "b"}, title="t"),
        view_center={"lat": 50.08, "lon": 14.45},
        view_zoom=15.0,
        focus_map=True,
    )

    # We clamp zoom-out to avoid huge jumps; allow up to ~2 zoom levels out from current.
    assert float(plot["layout"]["mapbox"]["zoom"]) >= 13.0

