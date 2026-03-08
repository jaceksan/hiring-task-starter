import math

import pytest
from layers.types import Layer, LayerBundle, LineFeature, PointFeature, PolygonFeature
from lod.points import ClusterMarker
from plotly.build_map import build_map_plot
from plotly.types import Highlight


def test_build_map_plot_shape():
    bundle = LayerBundle(
        layers=[
            Layer(
                id="places",
                kind="points",
                title="Places (points)",
                features=[
                    PointFeature(id="p1", lon=14.4, lat=50.08, props={"name": "A"})
                ],
                style={},
            ),
            Layer(
                id="roads",
                kind="lines",
                title="Roads (lines)",
                features=[
                    LineFeature(
                        id="r1",
                        coords=[(14.39, 50.07), (14.42, 50.09)],
                        props={"name": "Road 1", "fclass": "primary"},
                    )
                ],
                style={},
            ),
            Layer(
                id="flood_zones",
                kind="polygons",
                title="Flood zones (polygons)",
                features=[
                    PolygonFeature(
                        id="f1",
                        rings=[
                            [(14.3, 50.0), (14.35, 50.0), (14.35, 50.05), (14.3, 50.05)]
                        ],
                        props={"flood_risk_level": "high"},
                    )
                ],
                style={},
            ),
        ]
    )
    plot = build_map_plot(bundle)

    assert set(plot.keys()) == {"data", "layout"}
    assert isinstance(plot["data"], list)
    assert isinstance(plot["layout"], dict)
    assert len(plot["data"]) >= 3

    # Ensure it's a Mapbox plotly payload (frontend expects scattermapbox)
    assert "mapbox" in plot["layout"]
    assert any(trace.get("type") == "scattermapbox" for trace in plot["data"])

    names = {t.get("name") for t in plot["data"]}
    assert "Places (points)" in names
    assert "Roads (lines)" in names
    assert any(
        isinstance(n, str) and n.startswith("Flood zones (polygons)") for n in names
    )


def test_build_map_plot_supports_multiple_highlight_overlays():
    bundle = LayerBundle(
        layers=[
            Layer(
                id="places",
                kind="points",
                title="Places (points)",
                features=[
                    PointFeature(id="node/1", lon=14.4, lat=50.08, props={"name": "A"}),
                    PointFeature(
                        id="node/2", lon=14.42, lat=50.09, props={"name": "B"}
                    ),
                ],
                style={},
            ),
            Layer(
                id="roads",
                kind="lines",
                title="Roads (lines)",
                features=[
                    LineFeature(
                        id="way/1",
                        coords=[(14.39, 50.07), (14.42, 50.09)],
                        props={"name": "Road 1", "fclass": "primary"},
                    )
                ],
                style={},
            ),
        ]
    )
    flooded = Highlight(
        layer_id="places",
        feature_ids={"node/1", "node/2"},
        title="Flooded places",
        mode="prompt",
    )
    transit = Highlight(
        layer_id="roads",
        feature_ids={"way/1"},
        title="Escape roads",
        mode="prompt",
    )
    plot = build_map_plot(
        bundle, highlights=[flooded, transit], highlight_source_layers=bundle
    )
    meta = (plot.get("layout") or {}).get("meta") or {}
    highlights = meta.get("highlights") or []
    assert isinstance(highlights, list)
    assert len(highlights) == 2
    stats = meta.get("stats") or {}
    assert stats.get("highlightRequested") == 3
    assert isinstance(stats.get("highlightOverlays"), list)


def test_highlighted_points_keep_place_hover_details():
    bundle = LayerBundle(
        layers=[
            Layer(
                id="places",
                kind="points",
                title="Places (points)",
                features=[
                    PointFeature(
                        id="node/1",
                        lon=14.4,
                        lat=50.08,
                        props={
                            "name": "Alpha",
                            "fclass": "townhall",
                            "place_category": "public_services",
                            "place_source": "osm",
                            "population": 42,
                        },
                    )
                ],
                style={},
            )
        ]
    )
    flooded = Highlight(
        layer_id="places",
        feature_ids={"node/1"},
        title="Flooded places",
        mode="prompt",
    )
    plot = build_map_plot(bundle, highlights=[flooded], highlight_source_layers=bundle)
    trace = next(t for t in plot["data"] if t.get("name") == "Flooded places")
    assert trace.get("mode") == "markers"
    assert trace.get("hovertemplate") == "%{text}<extra></extra>"
    text = trace.get("text") or []
    assert any("Alpha" in x for x in text)
    assert any("class: townhall" in x for x in text)
    assert any("category: Public Services" in x for x in text)
    assert any("source: osm" in x for x in text)
    assert any("population: 42" in x for x in text)


def test_build_map_plot_uses_flood_risk_bands_and_hover_metadata():
    flood_layer = Layer(
        id="flood_zones",
        kind="polygons",
        title="Flood zones (polygons)",
        features=[
            PolygonFeature(
                id="f1",
                rings=[[(14.0, 50.0), (14.1, 50.0), (14.1, 50.1), (14.0, 50.1)]],
                props={"flood_risk_level": "high", "water_name": "Vltava"},
            ),
            PolygonFeature(
                id="f2",
                rings=[[(14.2, 50.0), (14.3, 50.0), (14.3, 50.1), (14.2, 50.1)]],
                props={"flood_risk_level": "medium", "water_name": "Berounka"},
            ),
        ],
        style={
            "fillcolor": "rgba(30, 136, 229, 0.09)",
            "line": {"color": "rgba(30, 136, 229, 0.28)", "width": 1},
        },
        metadata={
            "floodRisk": {
                "property": "flood_risk_level",
                "waterEntityProperty": "water_name",
                "bands": [
                    {
                        "id": "high",
                        "label": "High (100y)",
                        "value": "high",
                        "fillColor": "rgba(229, 57, 53, 0.10)",
                        "lineColor": "rgba(229, 57, 53, 0.34)",
                    },
                    {
                        "id": "medium",
                        "label": "Medium (50y+)",
                        "value": "medium",
                        "fillColor": "rgba(255, 183, 77, 0.08)",
                        "lineColor": "rgba(245, 124, 0, 0.30)",
                    },
                ],
                "defaultFillColor": "rgba(30, 136, 229, 0.09)",
            }
        },
    )
    bundle = LayerBundle(layers=[flood_layer])
    plot = build_map_plot(bundle)
    traces = plot.get("data") or []
    names = {t.get("name") for t in traces}
    assert "Flood zones (polygons) - High (100y)" in names
    assert "Flood zones (polygons) - Medium (50y+)" in names

    high = next(
        t for t in traces if t.get("name") == "Flood zones (polygons) - High (100y)"
    )
    assert high.get("fillcolor") == "rgba(229, 57, 53, 0.10)"
    assert high.get("line", {}).get("color") == "rgba(229, 57, 53, 0.34)"
    text = [x for x in (high.get("text") or []) if isinstance(x, str)]
    assert any("Risk: High (100y)" in x for x in text)
    assert any("Water: Vltava" in x for x in text)


def test_trace_point_clusters_uses_lighter_density_palette():
    bundle = LayerBundle(
        layers=[
            Layer(
                id="places",
                kind="points",
                title="Places (points)",
                features=[],
                style={},
            )
        ]
    )
    plot = build_map_plot(
        bundle,
        clusters=[
            ClusterMarker(
                lon=14.4,
                lat=50.08,
                count=25,
                cell_x=1,
                cell_y=2,
                exact_count=25,
                bin_size_m=1000.0,
            )
        ],
        cluster_layer_id="places",
    )
    density = next(
        t for t in plot["data"] if t.get("name") == "Places (points) (density)"
    )
    z = density.get("z") or []
    assert len(z) == 1
    assert z[0] == pytest.approx(math.log1p(25.0))
    assert density.get("zmin") == 0.0
    assert density.get("zmax") == pytest.approx(math.log1p(25.0))
    assert density.get("opacity") == 0.2
    assert density.get("colorscale") == [
        [0.0, "#fffef7"],
        [0.25, "#fff8dd"],
        [0.5, "#ffefb8"],
        [0.75, "#f4dda0"],
        [1.0, "#e7c77a"],
    ]
    assert density.get("marker", {}).get("line") == {
        "color": "rgba(138, 111, 44, 0.06)",
        "width": 0.1,
    }


def test_build_map_plot_respects_inspect_mode_hover_priority():
    bundle = LayerBundle(
        layers=[
            Layer(
                id="roads",
                kind="lines",
                title="Roads (lines)",
                features=[
                    LineFeature(
                        id="r1",
                        coords=[(14.39, 50.07), (14.42, 50.09)],
                        props={"name": "Road 1", "fclass": "primary"},
                    )
                ],
                style={},
            ),
            Layer(
                id="places",
                kind="points",
                title="Places (points)",
                features=[PointFeature(id="p1", lon=14.4, lat=50.08, props={"name": "A"})],
                style={},
            ),
        ]
    )
    plot = build_map_plot(bundle, inspect_mode="places")
    roads = next(t for t in plot["data"] if t.get("name") == "Roads (lines)")
    places = next(t for t in plot["data"] if t.get("name") == "Places (points)")
    assert roads.get("hoverinfo") == "skip"
    assert places.get("hovertemplate") == "%{text}<extra></extra>"
