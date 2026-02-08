from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

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
) -> dict[str, Any]:
    traces: list[dict[str, Any]] = []

    traces.append(_trace_flood_polygons(layers.flood_q100))
    traces.append(_trace_metro_lines(layers.metro_ways))
    traces.append(_trace_beer_points(layers.beer_pois))

    if highlight and highlight.point_ids:
        traces.append(_trace_highlight_points(layers.beer_pois, highlight))

    return {
        "data": traces,
        "layout": {
            "mapbox": {
                "center": {"lat": 50.0755, "lon": 14.4378},
                "zoom": 10.5,
                "style": "carto-positron",
            },
            "showlegend": True,
        },
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

