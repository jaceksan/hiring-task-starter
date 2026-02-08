from __future__ import annotations

from geo.aoi import BBox
from geo.index import build_geo_index
from layers.types import Layer, LayerBundle, PointFeature, PolygonFeature
from scenarios.types import ScenarioHighlightRule, ScenarioRouting

from agent.router import route_prompt


def test_highlight_rule_selects_points_in_mask():
    # Square polygon around (0,0)-(2,2), plus 2 points inside and 1 outside.
    poly = PolygonFeature(
        id="poly",
        rings=[[(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)]],
        props={},
    )
    pts = [
        PointFeature(id="in1", lon=1.0, lat=1.0, props={"name": "A"}),
        PointFeature(id="in2", lon=1.5, lat=1.5, props={"name": "B"}),
        PointFeature(id="out", lon=5.0, lat=5.0, props={"name": "C"}),
    ]
    bundle = LayerBundle(
        layers=[
            Layer(id="mask", kind="polygons", title="Mask", features=[poly], style={}),
            Layer(id="points", kind="points", title="Points", features=pts, style={}),
        ]
    )
    index = build_geo_index(bundle)

    routing = ScenarioRouting(
        primaryPointsLayerId="points",
        maskPolygonsLayerId="mask",
        pointLabelSingular="place",
        pointLabelPlural="places",
        maskLabel="water",
        showLayersKeywords=["show layers"],
        countKeywords=["how many"],
        maskKeywords=["flooded"],
        recommendKeywords=["recommend"],
        proximity=[],
        highlightRules=[
            ScenarioHighlightRule(
                keywords=["show flooded places"],
                layerId="points",
                title="Flooded places",
                maxFeatures=50,
                maskLayerId="mask",
                maskMode="IN_MASK",
            )
        ],
    )

    resp = route_prompt(
        "show flooded places",
        layers=bundle,
        index=index,
        aoi=BBox(min_lon=-1, min_lat=-1, max_lon=3, max_lat=3),
        routing=routing,
    )
    assert resp.highlight is not None
    assert resp.highlight.layer_id == "points"
    assert resp.highlight.feature_ids == {"in1", "in2"}

