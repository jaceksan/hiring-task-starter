from __future__ import annotations

from typing import Any

from geo.aoi import BBox
from lod.points import ClusterMarker, cap_points
from lod.simplify import simplify_lines_until_budget, simplify_polygons_until_budget
from layers.types import (
    Layer,
    LayerBundle,
    LineFeature,
    PointFeature,
    PolygonFeature,
)
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
    highlights: list[Highlight] | None = None,
    highlight_source_layers: LayerBundle | None = None,
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

    # Highlight overlay should not silently disappear due to LOD/caps.
    # Build overlays from the raw (pre-LOD) layer bundle when available, but
    # simplify/cap them separately to keep rendering responsive.
    active_highlights = [
        h
        for h in (highlights or ([] if highlight is None else [highlight]))
        if h.feature_ids
    ]
    highlight_stats: list[dict[str, Any]] = []
    src = highlight_source_layers or layers
    zoom_for_budget = float(view_zoom) if view_zoom is not None else 10.0
    for hl_req in active_highlights:
        hl = src.get(hl_req.layer_id)
        ids = set(hl_req.feature_ids)

        def match(fid: str) -> bool:
            if fid in ids:
                return True
            base = (fid or "").split(":", 1)[0]
            return bool(base) and base in ids

        rendered = 0
        if hl is not None and hl.kind == "points":
            feats = [
                f for f in hl.features if isinstance(f, PointFeature) and match(f.id)
            ]
            feats = cap_points(feats, 5_000, keep_ids=set(f.id for f in feats))
            rendered = len(feats)
            traces.append(
                trace_highlight_layer(
                    LayerBundle(
                        layers=[
                            Layer(
                                id=hl.id,
                                kind=hl.kind,
                                title=hl.title,
                                features=feats,
                                style=hl.style,
                            )
                        ]
                    ),
                    hl_req,
                )
            )
        elif hl is not None and hl.kind == "lines":
            feats = [
                f for f in hl.features if isinstance(f, LineFeature) and match(f.id)
            ]
            feats = simplify_lines_until_budget(
                feats, zoom_for_budget, max_vertices=60_000, keep_ids=ids
            )
            rendered = len(feats)
            traces.append(
                trace_highlight_layer(
                    LayerBundle(
                        layers=[
                            Layer(
                                id=hl.id,
                                kind=hl.kind,
                                title=hl.title,
                                features=feats,
                                style=hl.style,
                            )
                        ]
                    ),
                    hl_req,
                )
            )
        elif hl is not None and hl.kind == "polygons":
            feats = [
                f for f in hl.features if isinstance(f, PolygonFeature) and match(f.id)
            ]
            feats = simplify_polygons_until_budget(
                feats, zoom_for_budget, max_vertices=80_000, keep_ids=ids
            )
            rendered = len(feats)
            traces.append(
                trace_highlight_layer(
                    LayerBundle(
                        layers=[
                            Layer(
                                id=hl.id,
                                kind=hl.kind,
                                title=hl.title,
                                features=feats,
                                style=hl.style,
                            )
                        ]
                    ),
                    hl_req,
                )
            )
        else:
            traces.append(trace_highlight_layer(layers, hl_req))
        highlight_stats.append(
            {
                "layerId": hl_req.layer_id,
                "title": hl_req.title or "Highlighted",
                "mode": hl_req.mode,
                "requested": len(ids),
                "rendered": int(rendered),
            }
        )

    center = view_center or {"lat": 0.0, "lon": 0.0}
    zoom = float(view_zoom) if view_zoom is not None else 2.0

    if focus_map and active_highlights:
        selected: list[PointFeature] = []
        for hl_req in active_highlights:
            selected.extend(
                selected_points(layers, hl_req.layer_id, hl_req.feature_ids)
            )
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
    if active_highlights:
        meta["highlight"] = {
            "layerId": active_highlights[0].layer_id,
            "featureIds": sorted(active_highlights[0].feature_ids),
            "title": active_highlights[0].title or "Highlighted",
            "mode": active_highlights[0].mode,
        }
        meta["highlights"] = [
            {
                "layerId": h.layer_id,
                "featureIds": sorted(h.feature_ids),
                "title": h.title or "Highlighted",
                "mode": h.mode,
            }
            for h in active_highlights
        ]

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
    highlight_requested = sum(h["requested"] for h in highlight_stats)
    highlight_rendered = sum(h["rendered"] for h in highlight_stats)

    meta["stats"] = {
        "clusterMode": clusters is not None,
        "renderedPoints": pts,
        "renderedLines": lines,
        "renderedPolygons": polys,
        "renderedClusters": len(clusters) if clusters is not None else 0,
        "highlightRequested": highlight_requested,
        "highlightRendered": highlight_rendered,
        "highlightOverlays": highlight_stats,
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
