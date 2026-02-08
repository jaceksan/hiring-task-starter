from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from geo.aoi import BBox
from lod.policy import ClusterMarker
from layers.types import Layer, LayerBundle, LineFeature, PointFeature, PolygonFeature


@dataclass(frozen=True)
class Highlight:
    """
    Optional emphasis for a subset of features in a single point layer.
    """

    layer_id: str
    feature_ids: set[str]
    title: str | None = None


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
        traces.append(_trace_aoi_bbox(aoi))

    # Render layers in a stable order: polygons -> lines -> points.
    for l in layers.of_kind("polygons"):
        traces.append(_trace_polygons(l))
    for l in layers.of_kind("lines"):
        traces.append(_trace_lines(l))
    for l in layers.of_kind("points"):
        if clusters is not None and cluster_layer_id and l.id == cluster_layer_id:
            traces.append(_trace_point_clusters(l, clusters))
        else:
            traces.append(_trace_points(l))

    if highlight and highlight.feature_ids:
        traces.append(_trace_highlight_layer(layers, highlight))

    center = view_center or {"lat": 0.0, "lon": 0.0}
    zoom = float(view_zoom) if view_zoom is not None else 2.0

    if focus_map and highlight and highlight.feature_ids:
        selected = _selected_points(layers, highlight.layer_id, highlight.feature_ids)
        if selected:
            fit_center, fit_zoom = _fit_view_to_points(selected, viewport=viewport)
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
    pts = sum(len(l.features) for l in layers.of_kind("points"))
    lines = sum(len(l.features) for l in layers.of_kind("lines"))
    polys = sum(len(l.features) for l in layers.of_kind("polygons"))
    line_vertices = sum(len(f.coords) for l in layers.of_kind("lines") for f in l.features if isinstance(f, LineFeature))
    poly_vertices = sum(len(r) for l in layers.of_kind("polygons") for f in l.features if isinstance(f, PolygonFeature) for r in f.rings)
    highlight_count = 0
    if highlight and highlight.feature_ids:
        highlight_count = len(_selected_points(layers, highlight.layer_id, highlight.feature_ids))

    meta["stats"] = {
        "clusterMode": clusters is not None,
        "renderedPoints": pts,
        "renderedLines": lines,
        "renderedPolygons": polys,
        "renderedClusters": len(clusters) if clusters is not None else 0,
        "renderedHighlightPoints": highlight_count,
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


def _trace_aoi_bbox(aoi: BBox) -> dict[str, Any]:
    b = aoi.normalized()
    lons = [b.min_lon, b.max_lon, b.max_lon, b.min_lon, b.min_lon]
    lats = [b.min_lat, b.min_lat, b.max_lat, b.max_lat, b.min_lat]
    return {
        "type": "scattermapbox",
        "name": "AOI (viewport bbox)",
        "lon": lons,
        "lat": lats,
        "mode": "lines",
        "line": {"color": "rgba(55, 71, 79, 0.7)", "width": 1},
        "hoverinfo": "skip",
        "showlegend": False,
    }


def _trace_polygons(layer: Layer) -> dict[str, Any]:
    lons: list[float | None] = []
    lats: list[float | None] = []
    feats = [f for f in layer.features if isinstance(f, PolygonFeature)]
    for f in feats:
        if not f.rings:
            continue
        ring = f.rings[0]
        if not ring:
            continue
        if ring[0] != ring[-1]:
            ring = [*ring, ring[0]]
        for lon, lat in ring:
            lons.append(lon)
            lats.append(lat)
        lons.append(None)
        lats.append(None)

    style = layer.style or {}
    line = style.get("line") or {}
    return {
        "type": "scattermapbox",
        "name": layer.title,
        "lon": lons,
        "lat": lats,
        "mode": "lines",
        "fill": "toself",
        "fillcolor": style.get("fillcolor") or "rgba(30, 136, 229, 0.20)",
        "line": {
            "color": (line.get("color") if isinstance(line, dict) else None) or "rgba(30, 136, 229, 0.65)",
            "width": int((line.get("width") if isinstance(line, dict) else 1) or 1),
        },
        "hoverinfo": "skip",
    }


def _trace_lines(layer: Layer) -> dict[str, Any]:
    lons: list[float | None] = []
    lats: list[float | None] = []
    feats = [f for f in layer.features if isinstance(f, LineFeature)]
    for f in feats:
        if len(f.coords) < 2:
            continue
        for lon, lat in f.coords:
            lons.append(lon)
            lats.append(lat)
        lons.append(None)
        lats.append(None)

    style = layer.style or {}
    line = style.get("line") or {}
    return {
        "type": "scattermapbox",
        "name": layer.title,
        "lon": lons,
        "lat": lats,
        "mode": "lines",
        "line": {
            "color": (line.get("color") if isinstance(line, dict) else None) or "rgba(67, 160, 71, 0.9)",
            "width": int((line.get("width") if isinstance(line, dict) else 2) or 2),
        },
        "hoverinfo": "skip",
    }


def _trace_points(layer: Layer) -> dict[str, Any]:
    feats = [f for f in layer.features if isinstance(f, PointFeature)]
    style = layer.style or {}
    marker = style.get("marker") or {}
    return {
        "type": "scattermapbox",
        "name": layer.title,
        "lon": [p.lon for p in feats],
        "lat": [p.lat for p in feats],
        "mode": "markers",
        "text": [str((p.props or {}).get("label") or (p.props or {}).get("name") or "") for p in feats],
        "marker": {
            "size": int((marker.get("size") if isinstance(marker, dict) else 6) or 6),
            "color": (marker.get("color") if isinstance(marker, dict) else None) or "rgba(255, 193, 7, 0.75)",
        },
        "hovertemplate": "%{text}<extra></extra>",
    }


def _trace_point_clusters(layer: Layer, clusters: list[ClusterMarker]) -> dict[str, Any]:
    # Style inherits from the point layer, but with cluster-specific defaults.
    style = layer.style or {}
    marker = style.get("marker") or {}
    color = (marker.get("color") if isinstance(marker, dict) else None) or "rgba(255, 193, 7, 0.55)"
    return {
        "type": "scattermapbox",
        "name": f"{layer.title} (clusters)",
        "lon": [c.lon for c in clusters],
        "lat": [c.lat for c in clusters],
        "mode": "markers+text",
        "text": [str(c.count) for c in clusters],
        "textposition": "middle center",
        "marker": {
            "size": [min(26, 8 + int(c.count**0.5) * 2) for c in clusters],
            "color": color,
            "line": {"color": "rgba(255, 193, 7, 0.9)", "width": 1},
        },
        "hovertemplate": "%{text}<extra></extra>",
    }


def _trace_highlight_layer(layers: LayerBundle, highlight: Highlight) -> dict[str, Any]:
    layer = layers.get(highlight.layer_id)
    if layer is None:
        return {"type": "scattermapbox", "name": highlight.title or "Highlighted", "lon": [], "lat": []}

    if layer.kind == "points":
        selected = _selected_points(layers, highlight.layer_id, highlight.feature_ids)
        return {
            "type": "scattermapbox",
            "name": highlight.title or "Highlighted",
            "lon": [p.lon for p in selected],
            "lat": [p.lat for p in selected],
            "mode": "markers+text",
            "text": [str((p.props or {}).get("label") or (p.props or {}).get("name") or "") for p in selected],
            "textposition": "top center",
            "marker": {"size": 11, "color": "rgba(229, 57, 53, 0.95)"},
            "hovertemplate": "%{text}<extra></extra>",
        }

    if layer.kind == "lines":
        feats = [f for f in layer.features if isinstance(f, LineFeature) and f.id in highlight.feature_ids]
        lons: list[float | None] = []
        lats: list[float | None] = []
        for f in feats:
            if len(f.coords) < 2:
                continue
            for lon, lat in f.coords:
                lons.append(lon)
                lats.append(lat)
            lons.append(None)
            lats.append(None)
        return {
            "type": "scattermapbox",
            "name": highlight.title or "Highlighted",
            "lon": lons,
            "lat": lats,
            "mode": "lines",
            "line": {"color": "rgba(229, 57, 53, 0.95)", "width": 4},
            "hoverinfo": "skip",
        }

    if layer.kind == "polygons":
        feats = [f for f in layer.features if isinstance(f, PolygonFeature) and f.id in highlight.feature_ids]
        lons: list[float | None] = []
        lats: list[float | None] = []
        for f in feats:
            if not f.rings:
                continue
            ring = f.rings[0]
            if not ring:
                continue
            if ring[0] != ring[-1]:
                ring = [*ring, ring[0]]
            for lon, lat in ring:
                lons.append(lon)
                lats.append(lat)
            lons.append(None)
            lats.append(None)
        return {
            "type": "scattermapbox",
            "name": highlight.title or "Highlighted",
            "lon": lons,
            "lat": lats,
            "mode": "lines",
            "fill": "toself",
            "fillcolor": "rgba(229, 57, 53, 0.15)",
            "line": {"color": "rgba(229, 57, 53, 0.95)", "width": 2},
            "hoverinfo": "skip",
        }

    return {"type": "scattermapbox", "name": highlight.title or "Highlighted", "lon": [], "lat": []}


def _selected_points(layers: LayerBundle, layer_id: str, ids: set[str]) -> list[PointFeature]:
    layer = layers.get(layer_id)
    if layer is None or layer.kind != "points":
        return []
    pts = [f for f in layer.features if isinstance(f, PointFeature)]
    return [p for p in pts if p.id in ids]


def _fit_view_to_points(
    points: list[PointFeature],
    *,
    viewport: dict[str, int] | None,
) -> tuple[dict[str, float], float]:
    min_lon = min(p.lon for p in points)
    max_lon = max(p.lon for p in points)
    min_lat = min(p.lat for p in points)
    max_lat = max(p.lat for p in points)

    pad_lon = max(0.003, (max_lon - min_lon) * 1.00)
    pad_lat = max(0.003, (max_lat - min_lat) * 1.00)
    min_lon -= pad_lon
    max_lon += pad_lon
    min_lat -= pad_lat
    max_lat += pad_lat

    center = {"lon": (min_lon + max_lon) / 2.0, "lat": (min_lat + max_lat) / 2.0}

    # Approximate Mapbox zoom needed to fit bbox into viewport.
    width = int((viewport or {}).get("width") or 900)
    height = int((viewport or {}).get("height") or 600)
    zoom = _bbox_to_zoom(min_lon, min_lat, max_lon, max_lat, width=width, height=height)
    return center, zoom


def _bbox_to_zoom(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    *,
    width: int,
    height: int,
) -> float:
    # WebMercator bbox -> zoom heuristic.
    import math

    def lat_to_rad(lat: float) -> float:
        s = math.sin(lat * math.pi / 180.0)
        return math.log((1 + s) / (1 - s)) / 2.0

    lat_rad_min = lat_to_rad(min_lat)
    lat_rad_max = lat_to_rad(max_lat)
    lon_delta = max_lon - min_lon
    lat_delta = (lat_rad_max - lat_rad_min) * 180.0 / math.pi

    # avoid division by zero
    lon_delta = max(lon_delta, 1e-6)
    lat_delta = max(lat_delta, 1e-6)

    # 256px tiles
    zoom_x = math.log2((width * 360.0) / (256.0 * lon_delta))
    zoom_y = math.log2((height * 170.0) / (256.0 * lat_delta))
    return float(min(zoom_x, zoom_y))

