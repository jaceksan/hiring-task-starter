from __future__ import annotations

from layers.types import Layer, LayerBundle, LineFeature, PointFeature, PolygonFeature
from lod.policy import LodBudgets, apply_lod


def test_cluster_points_reduces_count_when_over_budget():
    points = [
        PointFeature(id=f"p{i}", lon=14.4 + (i % 50) * 0.0001, lat=50.07 + (i // 50) * 0.0001, props={})
        for i in range(500)
    ]
    layers = LayerBundle(
        layers=[Layer(id="points", kind="points", title="Points", features=points, style={})]
    )

    lod_layers, clusters = apply_lod(
        layers,
        view_zoom=12.0,
        highlight_layer_id=None,
        highlight_feature_ids=None,
        cluster_points_layer_id="points",
        budgets=LodBudgets(max_points_rendered=50, max_line_vertices=10_000, max_poly_vertices=10_000),
    )

    assert clusters is not None
    assert len(clusters) < len(points)
    assert len(clusters) <= 50
    assert lod_layers.get("points").features == points  # clusters only affect rendering


def test_line_simplification_respects_vertex_budget():
    # A long polyline with many vertices.
    line = LineFeature(
        id="l",
        coords=[(14.0 + i * 0.00005, 50.0 + (i % 10) * 0.00001) for i in range(400)],
        props={},
    )
    layers = LayerBundle(
        layers=[Layer(id="lines", kind="lines", title="Lines", features=[line], style={})]
    )

    lod_layers, _clusters = apply_lod(
        layers,
        view_zoom=6.0,
        highlight_layer_id=None,
        highlight_feature_ids=None,
        cluster_points_layer_id="points",
        budgets=LodBudgets(max_points_rendered=10_000, max_line_vertices=60, max_poly_vertices=10_000),
    )

    out = lod_layers.get("lines")
    assert out is not None
    assert sum(len(f.coords) for f in out.features if isinstance(f, LineFeature)) <= 60


def test_polygon_simplification_respects_vertex_budget():
    # A \"circle-ish\" polygon with many vertices.
    ring = []
    for i in range(200):
        ring.append((14.4 + 0.01 * (i / 200), 50.07 + 0.01 * ((i * 7) % 200) / 200))
    ring.append(ring[0])

    poly = PolygonFeature(id="p", rings=[ring], props={})
    layers = LayerBundle(
        layers=[Layer(id="polys", kind="polygons", title="Polys", features=[poly], style={})]
    )

    lod_layers, _clusters = apply_lod(
        layers,
        view_zoom=6.0,
        highlight_layer_id=None,
        highlight_feature_ids=None,
        cluster_points_layer_id="points",
        budgets=LodBudgets(max_points_rendered=10_000, max_line_vertices=10_000, max_poly_vertices=80),
    )

    out = lod_layers.get("polys")
    assert out is not None
    assert sum(len(r) for p in out.features if isinstance(p, PolygonFeature) for r in p.rings) <= 80

