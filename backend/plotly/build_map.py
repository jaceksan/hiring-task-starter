from __future__ import annotations

from typing import Any

from geo.aoi import BBox
from lod.points import ClusterMarker
from layers.types import LayerBundle, LineFeature, PolygonFeature
from plotly.traces import (
    selected_points,
    trace_aoi_bbox,
    trace_highlight_layer,
    trace_lines,
    trace_point_clusters,
    trace_points,
    trace_polygons,
)
from plotly.types import Highlight
from plotly.view import fit_view_to_points


def build_map_plot(
    layers: LayerBundle,
    *,
    highlight: Highlight | None = None,
    aoi: BBox | None = None,
    view_center: dict[str, float] | None = None,
    view_zoom: float | None = None,
    viewport: dict[str, int] | None = None,
    focus_map: bool = False,
    clusters: list[ClusterMarker] | None = None,
    cluster_layer_id: str | None = None,
) -> dict[str, Any]:
    traces: list[dict[str, Any]] = []

    if aoi is not None:
        traces.append(trace_aoi_bbox(aoi))

    # Render layers in a stable order: polygons -> lines -> points.
    for layer in layers.of_kind("polygons"):
        traces.append(trace_polygons(layer))
    for layer in layers.of_kind("lines"):
        traces.append(trace_lines(layer))
    for layer in layers.of_kind("points"):
        if clusters is not None and cluster_layer_id and layer.id == cluster_layer_id:
            traces.append(trace_point_clusters(layer, clusters))
        else:
            traces.append(trace_points(layer))

    if highlight and highlight.feature_ids:
        traces.append(trace_highlight_layer(layers, highlight))

    center = view_center or {"lat": 0.0, "lon": 0.0}
    zoom = float(view_zoom) if view_zoom is not None else 2.0

    if focus_map and highlight and highlight.feature_ids:
        selected = selected_points(layers, highlight.layer_id, highlight.feature_ids)
        if selected:
            fit_center, fit_zoom = fit_view_to_points(selected, viewport=viewport)
            if view_zoom is not None:
                max_zoom_out = 2.0
                min_zoom = float(view_zoom) - max_zoom_out
                center = fit_center
                zoom = max(fit_zoom, min_zoom)
            else:
                center, zoom = fit_center, fit_zoom

    meta: dict[str, Any] = {}
    if highlight and highlight.feature_ids:
        meta["highlight"] = {
            "layerId": highlight.layer_id,
            "featureIds": sorted(highlight.feature_ids),
            "title": highlight.title or "Highlighted",
        }

    # Basic stats for HUD/telemetry.
    pts = sum(len(layer.features) for layer in layers.of_kind("points"))
    lines = sum(len(layer.features) for layer in layers.of_kind("lines"))
    polys = sum(len(layer.features) for layer in layers.of_kind("polygons"))
    line_vertices = sum(
        len(f.coords)
        for layer in layers.of_kind("lines")
        for f in layer.features
        if isinstance(f, LineFeature)
    )
    poly_vertices = sum(
        len(r)
        for layer in layers.of_kind("polygons")
        for f in layer.features
        if isinstance(f, PolygonFeature)
        for r in f.rings
    )
    highlight_requested = 0
    highlight_rendered = 0
    if highlight and highlight.feature_ids:
        highlight_requested = len(highlight.feature_ids)
        hl_layer = layers.get(highlight.layer_id)
        if hl_layer is not None:
            if hl_layer.kind == "points":
                highlight_rendered = len(
                    selected_points(layers, highlight.layer_id, highlight.feature_ids)
                )
            elif hl_layer.kind == "lines":
                highlight_rendered = sum(
                    1
                    for f in (hl_layer.features or [])
                    if isinstance(f, LineFeature) and f.id in highlight.feature_ids
                )
            elif hl_layer.kind == "polygons":
                highlight_rendered = sum(
                    1
                    for f in (hl_layer.features or [])
                    if isinstance(f, PolygonFeature) and f.id in highlight.feature_ids
                )

    meta["stats"] = {
        "clusterMode": clusters is not None,
        "renderedPoints": pts,
        "renderedLines": lines,
        "renderedPolygons": polys,
        "renderedClusters": len(clusters) if clusters is not None else 0,
        "highlightRequested": highlight_requested,
        "highlightRendered": highlight_rendered,
        "lineVertices": line_vertices,
        "polyVertices": poly_vertices,
    }

    return {
        "data": traces,
        "layout": {
            "mapbox": {
                "center": center,
                "zoom": zoom,
                "style": "carto-positron",
            },
            "showlegend": True,
            "legend": {
                "x": 0.99,
                "y": 0.99,
                "xanchor": "right",
                "yanchor": "top",
                "bgcolor": "rgba(255, 255, 255, 0.75)",
                "bordercolor": "rgba(120, 120, 120, 0.35)",
                "borderwidth": 1,
                "font": {"size": 11},
            },
            "meta": meta,
        },
    }
