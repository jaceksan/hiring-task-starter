from __future__ import annotations

from layers.types import Layer, LayerBundle, PointFeature
from lod.policy import LodBudgets, apply_lod


def test_lod_keeps_highlighted_points_on_aux_layer_when_over_budget():
    # Highlight is on an auxiliary (non-clustered) points layer.
    feats = [
        PointFeature(id=f"p{i}", lon=14.0 + i * 0.0001, lat=50.0, props={})
        for i in range(20)
    ]
    bundle = LayerBundle(
        layers=[
            Layer(id="primary", kind="points", title="Primary", features=[], style={}),
            Layer(id="aux", kind="points", title="Aux", features=feats, style={}),
        ]
    )

    lod, _clusters = apply_lod(
        bundle,
        view_zoom=10.0,
        highlight_layer_id="aux",
        highlight_feature_ids={"p17"},
        cluster_points_layer_id="primary",
        budgets=LodBudgets(max_aux_points_rendered=5),
    )

    aux = lod.get("aux")
    assert aux is not None
    ids = {f.id for f in aux.features}
    assert "p17" in ids
