from layers.load_scenario import load_scenario_layers
from plotly.build_map import build_map_plot
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
