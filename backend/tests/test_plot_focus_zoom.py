from __future__ import annotations

from layers.types import Layer, LayerBundle, PointFeature
from plotly.build_map import Highlight, build_map_plot


def test_focus_map_does_not_zoom_out_aggressively():
    layers = LayerBundle(
        layers=[
            Layer(
                id="points",
                kind="points",
                title="Points",
                features=[
                    PointFeature(id="a", lon=14.44, lat=50.08, props={}),
                    PointFeature(id="b", lon=14.46, lat=50.09, props={}),
                ],
                style={},
            )
        ]
    )

    plot = build_map_plot(
        layers,
        highlight=Highlight(layer_id="points", feature_ids={"a", "b"}, title="t"),
        view_center={"lat": 50.08, "lon": 14.45},
        view_zoom=15.0,
        focus_map=True,
        cluster_layer_id="points",
    )

    # We clamp zoom-out to avoid huge jumps; allow up to ~2 zoom levels out from current.
    assert float(plot["layout"]["mapbox"]["zoom"]) >= 13.0
