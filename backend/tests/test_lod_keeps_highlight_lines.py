from __future__ import annotations

from layers.types import Layer, LayerBundle, LineFeature, PointFeature
from lod.policy import LodBudgets, apply_lod


def test_lod_keeps_highlighted_lines_when_over_budget():
    # Two lines: one huge (will be dropped) and one small (should be kept).
    keep = LineFeature(
        id="keep",
        coords=[(14.0 + i * 0.0001, 50.0) for i in range(30)],
        props={"fclass": "motorway"},
    )
    huge = LineFeature(
        id="drop",
        coords=[(14.0 + i * 0.00001, 50.0 + (i % 10) * 0.00001) for i in range(500)],
        props={},
    )
    bundle = LayerBundle(
        layers=[
            Layer(id="roads", kind="lines", title="Roads", features=[keep, huge], style={}),
            Layer(id="places", kind="points", title="Places", features=[PointFeature(id="p", lon=14.0, lat=50.0, props={})], style={}),
        ]
    )

    lod, _clusters = apply_lod(
        bundle,
        view_zoom=6.0,
        highlight_layer_id="roads",
        highlight_feature_ids={"keep"},
        cluster_points_layer_id="places",
        budgets=LodBudgets(max_points_rendered=10_000, max_line_vertices=40, max_poly_vertices=10_000),
    )

    roads = lod.get("roads")
    assert roads is not None
    ids = {f.id for f in roads.features}
    assert "keep" in ids

