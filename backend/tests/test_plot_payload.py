from layers.types import Layer, LayerBundle, LineFeature, PointFeature, PolygonFeature
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
            "fillcolor": "rgba(30, 136, 229, 0.15)",
            "line": {"color": "rgba(30, 136, 229, 0.45)", "width": 1},
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
                        "fillColor": "rgba(229, 57, 53, 0.35)",
                        "lineColor": "rgba(229, 57, 53, 0.75)",
                    },
                    {
                        "id": "medium",
                        "label": "Medium (50y+)",
                        "value": "medium",
                        "fillColor": "rgba(251, 140, 0, 0.28)",
                        "lineColor": "rgba(251, 140, 0, 0.70)",
                    },
                ],
                "defaultFillColor": "rgba(30, 136, 229, 0.15)",
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
    assert high.get("fillcolor") == "rgba(229, 57, 53, 0.35)"
    assert high.get("line", {}).get("color") == "rgba(229, 57, 53, 0.75)"
    text = [x for x in (high.get("text") or []) if isinstance(x, str)]
    assert any("Risk: High (100y)" in x for x in text)
    assert any("Water: Vltava" in x for x in text)
