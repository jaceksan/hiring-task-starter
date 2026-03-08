from __future__ import annotations

from geo.aoi import BBox
from geo.index import build_geo_index
from layers.types import Layer, LayerBundle, LineFeature, PointFeature, PolygonFeature
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


def test_escape_roads_prompt_returns_points_and_roads_highlights():
    flood = PolygonFeature(
        id="f1",
        rings=[[(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)]],
        props={"flood_risk_level": "high"},
    )
    places = [
        PointFeature(id="p_in", lon=1.0, lat=1.0, props={"name": "In flood"}),
        PointFeature(id="p_out", lon=5.0, lat=5.0, props={"name": "Outside"}),
    ]
    roads = [
        LineFeature(
            id="r_escape",
            coords=[(1.0, 1.0), (3.0, 1.0)],
            props={"name": "Escape", "fclass": "primary"},
        ),
        LineFeature(
            id="r_flooded",
            coords=[(0.2, 0.2), (0.3, 0.3)],
            props={"name": "Flooded", "fclass": "residential"},
        ),
    ]
    bundle = LayerBundle(
        layers=[
            Layer(
                id="flood_zones",
                kind="polygons",
                title="Flood",
                features=[flood],
                style={},
            ),
            Layer(
                id="places", kind="points", title="Places", features=places, style={}
            ),
            Layer(id="roads", kind="lines", title="Roads", features=roads, style={}),
        ]
    )
    index = build_geo_index(bundle)
    routing = ScenarioRouting(
        primaryPointsLayerId="places",
        maskPolygonsLayerId="flood_zones",
        pointLabelSingular="place",
        pointLabelPlural="places",
        maskLabel="flood zones",
        showLayersKeywords=["show layers"],
        countKeywords=["how many"],
        maskKeywords=["flood"],
        recommendKeywords=["recommend"],
        proximity=[],
        highlightRules=[],
    )
    resp = route_prompt(
        "show me escape roads for places in flood zone",
        layers=bundle,
        index=index,
        aoi=BBox(min_lon=-1, min_lat=-1, max_lon=6, max_lat=6),
        routing=routing,
        request_context={"floodRiskLevel": "high"},
    )
    assert resp.highlights is not None
    assert any(h.layer_id == "places" for h in resp.highlights)
    assert any(h.layer_id == "roads" for h in resp.highlights)


def test_count_prompt_returns_points_and_active_flood_zone_highlights():
    flood = PolygonFeature(
        id="f1",
        rings=[[(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)]],
        props={"flood_risk_level": "high"},
    )
    places = [
        PointFeature(id="p_in", lon=1.0, lat=1.0, props={"name": "In flood"}),
        PointFeature(id="p_out", lon=5.0, lat=5.0, props={"name": "Outside"}),
    ]
    bundle = LayerBundle(
        layers=[
            Layer(
                id="flood_zones",
                kind="polygons",
                title="Flood",
                features=[flood],
                style={},
            ),
            Layer(
                id="places", kind="points", title="Places", features=places, style={}
            ),
        ]
    )
    index = build_geo_index(bundle)
    routing = ScenarioRouting(
        primaryPointsLayerId="places",
        maskPolygonsLayerId="flood_zones",
        pointLabelSingular="place",
        pointLabelPlural="places",
        maskLabel="flood zones",
        showLayersKeywords=["show layers"],
        countKeywords=["how many"],
        maskKeywords=["flood"],
        recommendKeywords=["recommend"],
        proximity=[],
        highlightRules=[],
    )

    resp = route_prompt(
        "how many places are flooded?",
        layers=bundle,
        index=index,
        aoi=BBox(min_lon=-1, min_lat=-1, max_lon=6, max_lat=6),
        routing=routing,
        request_context={"floodRiskLevel": "high"},
    )

    assert resp.highlight is not None
    assert resp.highlight.layer_id == "places"
    assert resp.highlight.feature_ids == {"p_in"}
    assert resp.highlights is not None
    assert any(h.layer_id == "places" and h.feature_ids == {"p_in"} for h in resp.highlights)
    assert any(h.layer_id == "flood_zones" and h.feature_ids == {"f1"} for h in resp.highlights)


def test_safest_prompt_respects_selected_flood_zones():
    flood_hi = PolygonFeature(
        id="f_hi",
        rings=[[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]],
        props={"flood_risk_level": "high"},
    )
    flood_other = PolygonFeature(
        id="f_other",
        rings=[[(3.0, 3.0), (4.0, 3.0), (4.0, 4.0), (3.0, 4.0), (3.0, 3.0)]],
        props={"flood_risk_level": "high"},
    )
    places = [
        PointFeature(id="p1", lon=1.5, lat=1.5, props={"name": "Safe near selected"}),
        PointFeature(id="p2", lon=3.5, lat=3.5, props={"name": "In unselected zone"}),
    ]
    roads = [
        LineFeature(
            id="r1",
            coords=[(1.45, 1.45), (1.9, 1.9)],
            props={"name": "R1", "fclass": "primary"},
        ),
        LineFeature(
            id="r2",
            coords=[(3.45, 3.45), (3.9, 3.9)],
            props={"name": "R2", "fclass": "primary"},
        ),
    ]
    bundle = LayerBundle(
        layers=[
            Layer(
                id="flood_zones",
                kind="polygons",
                title="Flood",
                features=[flood_hi, flood_other],
                style={},
            ),
            Layer(
                id="places", kind="points", title="Places", features=places, style={}
            ),
            Layer(id="roads", kind="lines", title="Roads", features=roads, style={}),
        ]
    )
    index = build_geo_index(bundle)
    routing = ScenarioRouting(
        primaryPointsLayerId="places",
        maskPolygonsLayerId="flood_zones",
        pointLabelSingular="place",
        pointLabelPlural="places",
        maskLabel="flood zones",
        showLayersKeywords=["show layers"],
        countKeywords=["how many"],
        maskKeywords=["flood"],
        recommendKeywords=["recommend"],
        proximity=[],
        highlightRules=[],
    )
    resp = route_prompt(
        "show safest nearby places outside selected flood risk with reachable roads",
        layers=bundle,
        index=index,
        aoi=BBox(min_lon=-1, min_lat=-1, max_lon=6, max_lat=6),
        routing=routing,
        request_context={
            "floodRiskLevel": "high",
            "selectedFloodZoneIds": ["f_hi"],
        },
    )
    assert resp.highlight is not None
    assert resp.highlight.layer_id == "places"
    # `p1` should remain eligible because only selected zone is active.
    assert "p1" in resp.highlight.feature_ids
