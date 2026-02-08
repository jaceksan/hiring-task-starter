from plotly.build_plot import build_prague_plot
from layers.load_prague import load_prague_layers


def test_build_prague_plot_shape():
    layers = load_prague_layers()
    plot = build_prague_plot(layers)

    assert set(plot.keys()) == {"data", "layout"}
    assert isinstance(plot["data"], list)
    assert isinstance(plot["layout"], dict)
    assert len(plot["data"]) >= 3

    # Ensure it's a Mapbox plotly payload (frontend expects scattermapbox)
    assert "mapbox" in plot["layout"]
    assert any(trace.get("type") == "scattermapbox" for trace in plot["data"])

