from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from geo.aoi import BBox
from layers.types import LineFeature, PointFeature, PolygonFeature, PragueLayers


@dataclass(frozen=True)
class Highlight:
    """
    Optional emphasis for a subset of points.
    """

    point_ids: set[str]
    title: str | None = None


def build_prague_plot(
    layers: PragueLayers,
    highlight: Highlight | None = None,
    aoi: BBox | None = None,
    view_center: dict[str, float] | None = None,
    view_zoom: float | None = None,
    focus_map: bool = False,
) -> dict[str, Any]:
    traces: list[dict[str, Any]] = []

    if aoi is not None:
        traces.append(_trace_aoi_bbox(aoi))
    traces.append(_trace_flood_polygons(layers.flood_q100))
    traces.append(_trace_metro_lines(layers.metro_ways))
    traces.append(_trace_beer_points(layers.beer_pois))

    if highlight and highlight.point_ids:
        traces.append(_trace_highlight_points(layers.beer_pois, highlight))

    center = view_center or {"lat": 50.0755, "lon": 14.4378}
    zoom = float(view_zoom) if view_zoom is not None else 10.5

    if focus_map and highlight and highlight.point_ids:
        selected = [p for p in layers.beer_pois if p.id in highlight.point_ids]
        if selected:
            center, zoom = _fit_view_to_points(selected)

    return {
        "data": traces,
        "layout": {
            "mapbox": {
                "center": center,
                "zoom": zoom,
                "style": "carto-positron",
            },
            "showlegend": True,
        },
    }


def _trace_aoi_bbox(aoi: BBox) -> dict[str, Any]:
    b = aoi.normalized()
    # Draw as a simple rectangle outline.
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


def _trace_flood_polygons(polys: Iterable[PolygonFeature]) -> dict[str, Any]:
    lons: list[float | None] = []
    lats: list[float | None] = []

    for f in polys:
        if not f.rings:
            continue
        # MVP: only outer ring (holes are ignored for simplicity)
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
        "name": "Flood extent (Q100)",
        "lon": lons,
        "lat": lats,
        "mode": "lines",
        "fill": "toself",
        "fillcolor": "rgba(30, 136, 229, 0.20)",
        "line": {"color": "rgba(30, 136, 229, 0.65)", "width": 1},
        "hoverinfo": "skip",
    }


def _trace_metro_lines(lines: Iterable[LineFeature]) -> dict[str, Any]:
    lons: list[float | None] = []
    lats: list[float | None] = []
    for f in lines:
        if len(f.coords) < 2:
            continue
        for lon, lat in f.coords:
            lons.append(lon)
            lats.append(lat)
        lons.append(None)
        lats.append(None)

    return {
        "type": "scattermapbox",
        "name": "Metro (OSM subway ways)",
        "lon": lons,
        "lat": lats,
        "mode": "lines",
        "line": {"color": "rgba(67, 160, 71, 0.9)", "width": 2},
        "hoverinfo": "skip",
    }


def _trace_beer_points(points: list[PointFeature]) -> dict[str, Any]:
    return {
        "type": "scattermapbox",
        "name": "Beer POIs (pub/biergarten/brewery)",
        "lon": [p.lon for p in points],
        "lat": [p.lat for p in points],
        "mode": "markers",
        "text": [p.props.get("label") or p.props.get("name") or "" for p in points],
        "marker": {"size": 6, "color": "rgba(255, 193, 7, 0.75)"},
        "hovertemplate": "%{text}<extra></extra>",
    }


def _trace_highlight_points(points: list[PointFeature], highlight: Highlight) -> dict[str, Any]:
    selected = [p for p in points if p.id in highlight.point_ids]
    return {
        "type": "scattermapbox",
        "name": highlight.title or "Highlighted",
        "lon": [p.lon for p in selected],
        "lat": [p.lat for p in selected],
        "mode": "markers+text",
        "text": [p.props.get("label") or p.props.get("name") or "" for p in selected],
        "textposition": "top center",
        "marker": {"size": 11, "color": "rgba(229, 57, 53, 0.95)"},
        "hovertemplate": "%{text}<extra></extra>",
    }


def _fit_view_to_points(points: list[PointFeature]) -> tuple[dict[str, float], float]:
    """
    Approximate a center+zoom that fits the provided points.

    We don't know the actual viewport size server-side; we use a reasonable default,
    which is good enough for a demo "focus results" behavior.
    """
    min_lon = min(p.lon for p in points)
    max_lon = max(p.lon for p in points)
    min_lat = min(p.lat for p in points)
    max_lat = max(p.lat for p in points)

    # Add padding so markers aren't on the edges.
    # This intentionally over-pads a bit because the server does not know the exact viewport size.
    pad_lon = max(0.002, (max_lon - min_lon) * 0.60)
    pad_lat = max(0.002, (max_lat - min_lat) * 0.60)
    min_lon -= pad_lon
    max_lon += pad_lon
    min_lat -= pad_lat
    max_lat += pad_lat

    center = {"lat": (min_lat + max_lat) / 2, "lon": (min_lon + max_lon) / 2}
    zoom = _approx_zoom_for_bbox(min_lon=min_lon, max_lon=max_lon, min_lat=min_lat, max_lat=max_lat)
    return center, zoom


def _approx_zoom_for_bbox(*, min_lon: float, max_lon: float, min_lat: float, max_lat: float) -> float:
    """
    Very rough WebMercator zoom approximation from bbox spans.
    """
    import math

    # Typical visible map area in this app (right panel).
    viewport_w = 900
    viewport_h = 650
    tile_size = 256

    lon_span = max(1e-6, abs(max_lon - min_lon))

    # Convert lat to mercator Y for a better vertical span estimate.
    def merc_y(lat_deg: float) -> float:
        lat_rad = math.radians(max(-85.0, min(85.0, lat_deg)))
        return math.log(math.tan(math.pi / 4 + lat_rad / 2))

    y_span = max(1e-6, abs(merc_y(max_lat) - merc_y(min_lat)))

    # Horizontal zoom (degrees -> pixels at zoom z): 360 / (tile_size * 2^z) deg per pixel.
    z_lon = math.log2((360.0 * viewport_w) / (tile_size * lon_span))
    # Vertical zoom (mercator y spans 2*pi across world)
    z_lat = math.log2(((2 * math.pi) * viewport_h) / (tile_size * y_span))

    z = min(z_lon, z_lat)
    # Back off slightly so all highlighted points are visible even with legends/side panels.
    z -= 0.9
    return float(max(2.0, min(16.5, z)))

