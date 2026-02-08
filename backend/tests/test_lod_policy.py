from __future__ import annotations

from layers.types import LineFeature, PointFeature, PolygonFeature, PragueLayers
from lod.policy import LodBudgets, apply_lod


def test_cluster_points_reduces_count_when_over_budget():
    points = [
        PointFeature(id=f"p{i}", lon=14.4 + (i % 50) * 0.0001, lat=50.07 + (i // 50) * 0.0001, props={})
        for i in range(500)
    ]
    layers = PragueLayers(flood_q100=[], metro_ways=[], beer_pois=points)

    lod_layers, clusters = apply_lod(
        layers,
        view_zoom=12.0,
        highlight_point_ids=None,
        budgets=LodBudgets(max_points_rendered=50, max_line_vertices=10_000, max_poly_vertices=10_000),
    )

    assert clusters is not None
    assert len(clusters) < len(points)
    assert lod_layers.beer_pois == points  # analysis points remain available; clusters only affect rendering


def test_line_simplification_respects_vertex_budget():
    # A long polyline with many vertices.
    line = LineFeature(
        id="l",
        coords=[(14.0 + i * 0.00005, 50.0 + (i % 10) * 0.00001) for i in range(400)],
        props={},
    )
    layers = PragueLayers(flood_q100=[], metro_ways=[line], beer_pois=[])

    lod_layers, _clusters = apply_lod(
        layers,
        view_zoom=6.0,
        highlight_point_ids=None,
        budgets=LodBudgets(max_points_rendered=10_000, max_line_vertices=60, max_poly_vertices=10_000),
    )

    assert sum(len(l.coords) for l in lod_layers.metro_ways) <= 60


def test_polygon_simplification_respects_vertex_budget():
    # A \"circle-ish\" polygon with many vertices.
    ring = []
    for i in range(200):
        ring.append((14.4 + 0.01 * (i / 200), 50.07 + 0.01 * ((i * 7) % 200) / 200))
    ring.append(ring[0])

    poly = PolygonFeature(id="p", rings=[ring], props={})
    layers = PragueLayers(flood_q100=[poly], metro_ways=[], beer_pois=[])

    lod_layers, _clusters = apply_lod(
        layers,
        view_zoom=6.0,
        highlight_point_ids=None,
        budgets=LodBudgets(max_points_rendered=10_000, max_line_vertices=10_000, max_poly_vertices=80),
    )

    assert sum(len(r) for p in lod_layers.flood_q100 for r in p.rings) <= 80

