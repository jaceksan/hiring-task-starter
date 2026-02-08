from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from lod.points import ClusterMarker, cap_points, cluster_points, should_cluster_points
from lod.simplify import simplify_lines_until_budget, simplify_polygons_until_budget
from layers.types import Layer, LayerBundle, LineFeature, PointFeature, PolygonFeature


@dataclass(frozen=True)
class LodBudgets:
    # Primary point layer (typically the one the agent highlights).
    max_points_rendered: int = 2_500
    # Other point layers (kept as actual points; no clustering).
    max_aux_points_rendered: int = 3_000
    max_line_vertices: int = 40_000
    max_poly_vertices: int = 80_000


def apply_lod(
    layers: LayerBundle,
    *,
    view_zoom: float,
    highlight_layer_id: str | None,
    highlight_feature_ids: set[str] | None,
    cluster_points_layer_id: str,
    budgets: LodBudgets | None = None,
) -> tuple[LayerBundle, list[ClusterMarker] | None]:
    """
    Apply zoom-aware level-of-detail policies.

    Important: LOD affects only the *rendered* payload. Spatial reasoning should run on
    the non-LOD features.
    """

    b = budgets or LodBudgets()
    zoom = float(view_zoom)

    poly_layers = [l for l in layers.layers if l.kind == "polygons"]
    line_layers = [l for l in layers.layers if l.kind == "lines"]
    point_layers = [l for l in layers.layers if l.kind == "points"]

    # Polygons: split budget evenly between polygon layers (simple, deterministic).
    poly_budget_each = max(0, int(b.max_poly_vertices // max(1, len(poly_layers))))
    poly_out: dict[str, list[PolygonFeature]] = {}
    for l in poly_layers:
        feats = [f for f in l.features if isinstance(f, PolygonFeature)]
        poly_out[l.id] = simplify_polygons_until_budget(
            feats, zoom, max_vertices=poly_budget_each
        )

    # Lines: split budget evenly between line layers.
    line_budget_each = max(0, int(b.max_line_vertices // max(1, len(line_layers))))
    line_out: dict[str, list[LineFeature]] = {}
    for l in line_layers:
        feats = [f for f in l.features if isinstance(f, LineFeature)]
        keep_ids = (
            set(highlight_feature_ids or set())
            if highlight_layer_id is not None and l.id == highlight_layer_id
            else None
        )
        line_out[l.id] = simplify_lines_until_budget(
            feats, zoom, max_vertices=line_budget_each, keep_ids=keep_ids
        )

    # Points: cluster/cap only the configured primary layer; cap others deterministically.
    beer_clusters: list[ClusterMarker] | None = None
    point_out: dict[str, list[PointFeature]] = {}
    for l in point_layers:
        feats = [f for f in l.features if isinstance(f, PointFeature)]
        if l.id == cluster_points_layer_id:
            if should_cluster_points(zoom, len(feats), b.max_points_rendered):
                beer_clusters = cluster_points(feats, zoom=zoom)[
                    : b.max_points_rendered
                ]
                point_out[l.id] = (
                    feats  # keep raw for highlight lookup; plot chooses clusters
                )
            elif len(feats) > b.max_points_rendered:
                keep_ids = (
                    set(highlight_feature_ids or set())
                    if highlight_layer_id is not None and l.id == highlight_layer_id
                    else None
                )
                point_out[l.id] = cap_points(
                    feats, b.max_points_rendered, keep_ids=keep_ids
                )
            else:
                point_out[l.id] = feats
        else:
            point_out[l.id] = (
                cap_points(feats, b.max_aux_points_rendered, keep_ids=None)
                if len(feats) > b.max_aux_points_rendered
                else feats
            )

    out_layers: list[Layer] = []
    for l in layers.layers:
        if l.kind == "polygons":
            feats = poly_out.get(l.id, [])
            out_layers.append(
                Layer(
                    id=l.id, kind=l.kind, title=l.title, features=feats, style=l.style
                )
            )
        elif l.kind == "lines":
            feats = line_out.get(l.id, [])
            out_layers.append(
                Layer(
                    id=l.id, kind=l.kind, title=l.title, features=feats, style=l.style
                )
            )
        elif l.kind == "points":
            feats = point_out.get(l.id, [])
            out_layers.append(
                Layer(
                    id=l.id, kind=l.kind, title=l.title, features=feats, style=l.style
                )
            )
        else:
            out_layers.append(l)

    return LayerBundle(layers=out_layers), beer_clusters
