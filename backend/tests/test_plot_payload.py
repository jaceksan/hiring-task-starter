from layers.load_scenario import load_scenario_layers
from plotly.build_map import build_map_plot
from plotly.types import Highlight
from scenarios.registry import get_scenario


def test_build_map_plot_shape():
    bundle = load_scenario_layers("prague_transport")
    plot = build_map_plot(bundle)

    assert set(plot.keys()) == {"data", "layout"}
    assert isinstance(plot["data"], list)
    assert isinstance(plot["layout"], dict)
    assert len(plot["data"]) >= 3

    # Ensure it's a Mapbox plotly payload (frontend expects scattermapbox)
    assert "mapbox" in plot["layout"]
    assert any(trace.get("type") == "scattermapbox" for trace in plot["data"])

    names = {t.get("name") for t in plot["data"]}
    cfg = get_scenario("prague_transport").config
    for layer_cfg in cfg.layers:
        assert layer_cfg.title in names


def test_build_map_plot_supports_multiple_highlight_overlays():
    bundle = load_scenario_layers("prague_transport")
    flooded = Highlight(
        layer_id="beer_pois",
        feature_ids={"node/1", "node/2"},
        title="Flooded pubs",
        mode="prompt",
    )
    transit = Highlight(
        layer_id="metro_ways",
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
