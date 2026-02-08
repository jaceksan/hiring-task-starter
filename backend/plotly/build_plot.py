from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from geo.aoi import BBox
from lod.policy import ClusterMarker
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
    viewport: dict[str, int] | None = None,
    focus_map: bool = False,
    beer_clusters: list[ClusterMarker] | None = None,
) -> dict[str, Any]:
    traces: list[dict[str, Any]] = []

    if aoi is not None:
        traces.append(_trace_aoi_bbox(aoi))
    traces.append(_trace_flood_polygons(layers.flood_q100))
    traces.append(_trace_metro_lines(layers.metro_ways))
    traces.append(_trace_metro_stations(layers.metro_stations))
    traces.append(_trace_tram_lines(layers.tram_ways))
    traces.append(_trace_tram_stops(layers.tram_stops))
    if beer_clusters is not None:
        traces.append(_trace_beer_clusters(beer_clusters))
    else:
        traces.append(_trace_beer_points(layers.beer_pois))

    if highlight and highlight.point_ids:
        traces.append(_trace_highlight_points(layers.beer_pois, highlight))

    center = view_center or {"lat": 50.0755, "lon": 14.4378}
    zoom = float(view_zoom) if view_zoom is not None else 10.5

    if focus_map and highlight and highlight.point_ids:
        selected = [p for p in layers.beer_pois if p.id in highlight.point_ids]
        if selected:
            fit_center, fit_zoom = _fit_view_to_points(selected, viewport=viewport)
            # The server doesn't know the exact client viewport; avoid aggressive zooming out.
            # We still allow zooming in (or a small zoom-out), but we keep the user's context.
            if view_zoom is not None:
                # Allow zooming out enough to include all highlights, but avoid huge jumps.
                # The right-side map viewport + labels/legend often require more zoom-out than the
                # raw bbox math suggests, so we allow a bit more than before.
                max_zoom_out = 2.0
                min_zoom = float(view_zoom) - max_zoom_out
                center = fit_center
                zoom = max(fit_zoom, min_zoom)
            else:
                center, zoom = fit_center, fit_zoom

    meta: dict[str, Any] = {}
    if highlight and highlight.point_ids:
        meta["highlight"] = {
            "pointIds": sorted(highlight.point_ids),
            "title": highlight.title or "Highlighted",
        }

    rendered_markers = len(beer_clusters) if beer_clusters is not None else len(layers.beer_pois)
    line_vertices = sum(len(l.coords) for l in layers.metro_ways) + sum(len(l.coords) for l in layers.tram_ways)
    poly_vertices = sum(len(r) for p in layers.flood_q100 for r in p.rings)
    highlight_count = 0
    if highlight and highlight.point_ids:
        highlight_count = sum(1 for p in layers.beer_pois if p.id in highlight.point_ids)

    meta["stats"] = {
        "clusterMode": beer_clusters is not None,
        "renderedMarkers": rendered_markers,
        "renderedClusters": len(beer_clusters) if beer_clusters is not None else 0,
        "renderedHighlightPoints": highlight_count,
        "lineVertices": line_vertices,
        "polyVertices": poly_vertices,
        "floodPolygons": len(layers.flood_q100),
        "metroLines": len(layers.metro_ways),
        "metroStations": len(layers.metro_stations),
        "tramLines": len(layers.tram_ways),
        "tramStops": len(layers.tram_stops),
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
            # Keep legend inside the map area (top-right) so the left sidebar stays clean.
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


def _trace_metro_stations(points: list[PointFeature]) -> dict[str, Any]:
    texts: list[str] = []
    hovertexts: list[str] = []
    for p in points:
        props = p.props or {}
        name = str(props.get("label") or props.get("name") or "").strip()
        railway = str(props.get("railway") or "").strip()

        # UX polish:
        # - station nodes should show just the station name (e.g. "Můstek")
        # - entrances/exits should show "Exit E102" (based on OSM `ref`) to avoid many duplicate
        #   station-name labels clustered around the same station.
        if railway == "subway_entrance":
            ref = str(props.get("ref") or "").strip()
            if ref:
                title = f"Exit {ref}"
            elif name:
                title = f"Exit {name}"
            else:
                title = "Exit"
        else:
            title = name or "Metro station"

        texts.append(title)
        hovertexts.append(f"<b>{title}</b>")

    return {
        "type": "scattermapbox",
        "name": "Metro stations/entrances",
        "lon": [p.lon for p in points],
        "lat": [p.lat for p in points],
        "mode": "markers",
        "text": texts,
        "hovertext": hovertexts,
        "marker": {
            "size": 8,
            "color": "rgba(27, 94, 32, 0.85)",
            "line": {"color": "rgba(27, 94, 32, 1.0)", "width": 1},
        },
        "hovertemplate": "%{hovertext}<extra></extra>",
    }


def _trace_tram_lines(lines: Iterable[LineFeature]) -> dict[str, Any]:
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
        "name": "Tram tracks (OSM tram ways)",
        "lon": lons,
        "lat": lats,
        "mode": "lines",
        "line": {"color": "rgba(156, 39, 176, 0.75)", "width": 1},
        "hoverinfo": "skip",
    }


def _trace_tram_stops(points: list[PointFeature]) -> dict[str, Any]:
    texts: list[str] = []
    hovertexts: list[str] = []
    for p in points:
        props = p.props or {}
        name = str(props.get("label") or props.get("name") or "").strip()
        title = name or "Tram stop"
        texts.append(title)

        lines: list[str] = [f"<b>{title}</b>"]
        ref = str(props.get("ref") or "").strip()
        if ref:
            lines.append(f"ref={ref}")
        operator = str(props.get("operator") or "").strip()
        if operator:
            lines.append(f"operator={operator}")
        network = str(props.get("network") or "").strip()
        if network:
            lines.append(f"network={network}")
        hovertexts.append("<br>".join(lines))

    return {
        "type": "scattermapbox",
        "name": "Tram stops/platforms",
        "lon": [p.lon for p in points],
        "lat": [p.lat for p in points],
        "mode": "markers",
        "text": texts,
        "hovertext": hovertexts,
        "marker": {
            "size": 6,
            "color": "rgba(106, 27, 154, 0.80)",
            "line": {"color": "rgba(106, 27, 154, 1.0)", "width": 1},
        },
        "hovertemplate": "%{hovertext}<extra></extra>",
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


def _trace_beer_clusters(clusters: list[ClusterMarker]) -> dict[str, Any]:
    return {
        "type": "scattermapbox",
        "name": "Beer POIs (clusters)",
        "lon": [c.lon for c in clusters],
        "lat": [c.lat for c in clusters],
        "mode": "markers+text",
        "text": [str(c.count) for c in clusters],
        "textposition": "middle center",
        "marker": {
            "size": [min(26, 8 + int(c.count**0.5) * 2) for c in clusters],
            "color": "rgba(255, 193, 7, 0.55)",
            "line": {"color": "rgba(255, 193, 7, 0.9)", "width": 1},
        },
        "hovertemplate": "%{text} places<extra></extra>",
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


def _fit_view_to_points(
    points: list[PointFeature],
    *,
    viewport: dict[str, int] | None,
) -> tuple[dict[str, float], float]:
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
    # We pad quite aggressively because:
    # - the right-side map viewport is smaller than the full window
    # - legends and marker labels take space
    # - Mapbox may cull markers near edges
    pad_lon = max(0.003, (max_lon - min_lon) * 1.00)
    pad_lat = max(0.003, (max_lat - min_lat) * 1.00)
    min_lon -= pad_lon
    max_lon += pad_lon
    min_lat -= pad_lat
    max_lat += pad_lat

    center = {"lat": (min_lat + max_lat) / 2, "lon": (min_lon + max_lon) / 2}
    zoom = _approx_zoom_for_bbox(
        min_lon=min_lon,
        max_lon=max_lon,
        min_lat=min_lat,
        max_lat=max_lat,
        viewport=viewport,
    )
    return center, zoom


def _approx_zoom_for_bbox(
    *,
    min_lon: float,
    max_lon: float,
    min_lat: float,
    max_lat: float,
    viewport: dict[str, int] | None,
) -> float:
    """
    Very rough WebMercator zoom approximation from bbox spans.
    """
    import math

    # Use real map viewport size if available; otherwise fall back to a reasonable default.
    viewport_w = int((viewport or {}).get("width") or 900)
    viewport_h = int((viewport or {}).get("height") or 650)
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
    z -= 1.3
    return float(max(2.0, min(16.0, z)))

