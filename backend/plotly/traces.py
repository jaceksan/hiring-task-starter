from __future__ import annotations

from typing import Any

from geo.aoi import BBox
from lod.points import ClusterMarker
from layers.types import Layer, LayerBundle, LineFeature, PointFeature, PolygonFeature
from plotly.types import Highlight


def _id_matches(fid: str, ids: set[str]) -> bool:
    if fid in ids:
        return True
    base = (fid or "").split(":", 1)[0]
    return bool(base) and base in ids


def trace_aoi_bbox(aoi: BBox) -> dict[str, Any]:
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


def _append_polygon_ring(
    *,
    lons: list[float | None],
    lats: list[float | None],
    texts: list[str | None],
    ring: list[tuple[float, float]],
    hover_text: str,
) -> None:
    if not ring:
        return
    closed = ring if ring[0] == ring[-1] else [*ring, ring[0]]
    for lon, lat in closed:
        lons.append(lon)
        lats.append(lat)
        texts.append(hover_text)
    lons.append(None)
    lats.append(None)
    texts.append(None)


def _trace_polygons(
    *,
    layer_name: str,
    features: list[PolygonFeature],
    fill_color: str,
    line_color: str,
    line_width: int,
    hover_label: str | None = None,
    water_entity_property: str | None = None,
    show_legend: bool = True,
) -> dict[str, Any]:
    lons: list[float | None] = []
    lats: list[float | None] = []
    texts: list[str | None] = []
    for f in features:
        if not f.rings:
            continue
        entity = None
        if water_entity_property:
            raw = (f.props or {}).get(water_entity_property)
            if isinstance(raw, str) and raw.strip():
                entity = raw.strip()
        if hover_label and entity:
            hover_text = f"{hover_label}<br>Water: {entity}"
        elif hover_label:
            hover_text = hover_label
        elif entity:
            hover_text = f"Water: {entity}"
        else:
            hover_text = ""
        _append_polygon_ring(
            lons=lons, lats=lats, texts=texts, ring=f.rings[0], hover_text=hover_text
        )

    return {
        "type": "scattermapbox",
        "name": layer_name,
        "lon": lons,
        "lat": lats,
        "text": texts,
        "mode": "lines",
        "fill": "toself",
        "fillcolor": fill_color,
        "line": {
            "color": line_color,
            "width": int(line_width),
        },
        "showlegend": show_legend,
        "hovertemplate": "%{text}<extra></extra>",
    }


def trace_polygons(layer: Layer) -> list[dict[str, Any]]:
    feats = [f for f in layer.features if isinstance(f, PolygonFeature)]
    style = layer.style or {}
    line = style.get("line") or {}
    default_fill = style.get("fillcolor") or "rgba(30, 136, 229, 0.20)"
    default_line = (
        line.get("color") if isinstance(line, dict) else None
    ) or "rgba(30, 136, 229, 0.65)"
    default_width = int((line.get("width") if isinstance(line, dict) else 1) or 1)

    flood = (
        (layer.metadata or {}).get("floodRisk")
        if isinstance(layer.metadata, dict)
        else None
    )
    if not isinstance(flood, dict):
        return [
            _trace_polygons(
                layer_name=layer.title,
                features=feats,
                fill_color=default_fill,
                line_color=default_line,
                line_width=default_width,
            )
        ]

    risk_prop = flood.get("property")
    if not isinstance(risk_prop, str) or not risk_prop.strip():
        return [
            _trace_polygons(
                layer_name=layer.title,
                features=feats,
                fill_color=default_fill,
                line_color=default_line,
                line_width=default_width,
            )
        ]
    risk_prop = risk_prop.strip()
    water_prop = flood.get("waterEntityProperty")
    water_prop = (
        water_prop.strip()
        if isinstance(water_prop, str) and water_prop.strip()
        else None
    )
    default_risk_fill = (
        flood.get("defaultFillColor")
        if isinstance(flood.get("defaultFillColor"), str)
        else default_fill
    )
    bands_raw = flood.get("bands")
    bands = bands_raw if isinstance(bands_raw, list) else []
    if not bands:
        return [
            _trace_polygons(
                layer_name=layer.title,
                features=feats,
                fill_color=default_fill,
                line_color=default_line,
                line_width=default_width,
                water_entity_property=water_prop,
            )
        ]

    band_buckets: list[dict[str, Any]] = []
    for band in bands:
        if not isinstance(band, dict):
            continue
        band_buckets.append(
            {
                "id": str(band.get("id") or ""),
                "label": str(band.get("label") or band.get("id") or ""),
                "value": band.get("value"),
                "min": band.get("min"),
                "max": band.get("max"),
                "fillColor": str(band.get("fillColor") or default_risk_fill),
                "lineColor": str(band.get("lineColor") or default_line),
                "features": [],
            }
        )
    if not band_buckets:
        return [
            _trace_polygons(
                layer_name=layer.title,
                features=feats,
                fill_color=default_fill,
                line_color=default_line,
                line_width=default_width,
                water_entity_property=water_prop,
            )
        ]

    unmatched: list[PolygonFeature] = []
    for feat in feats:
        raw = (feat.props or {}).get(risk_prop)
        matched = False
        for bucket in band_buckets:
            # Categorical match.
            if bucket["value"] is not None and raw is not None:
                if str(raw).strip().lower() == str(bucket["value"]).strip().lower():
                    bucket["features"].append(feat)
                    matched = True
                    break
            # Numeric range match.
            if bucket["min"] is not None or bucket["max"] is not None:
                try:
                    numeric = float(raw)
                except (TypeError, ValueError):
                    continue
                min_ok = bucket["min"] is None or numeric >= float(bucket["min"])
                max_ok = bucket["max"] is None or numeric <= float(bucket["max"])
                if min_ok and max_ok:
                    bucket["features"].append(feat)
                    matched = True
                    break
        if not matched:
            unmatched.append(feat)

    out: list[dict[str, Any]] = []
    for bucket in band_buckets:
        if not bucket["features"]:
            continue
        label = bucket["label"] or bucket["id"] or "Risk"
        out.append(
            _trace_polygons(
                layer_name=f"{layer.title} - {label}",
                features=bucket["features"],
                fill_color=bucket["fillColor"],
                line_color=bucket["lineColor"],
                line_width=default_width,
                hover_label=f"Risk: {label}",
                water_entity_property=water_prop,
                show_legend=True,
            )
        )

    if unmatched and out:
        out.append(
            _trace_polygons(
                layer_name=f"{layer.title} - Other",
                features=unmatched,
                fill_color=default_risk_fill,
                line_color=default_line,
                line_width=default_width,
                hover_label="Risk: Other",
                water_entity_property=water_prop,
                show_legend=True,
            )
        )

    return out or [
        _trace_polygons(
            layer_name=layer.title,
            features=feats,
            fill_color=default_risk_fill,
            line_color=default_line,
            line_width=default_width,
            water_entity_property=water_prop,
        )
    ]


def trace_lines(layer: Layer) -> dict[str, Any]:
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
            "color": (line.get("color") if isinstance(line, dict) else None)
            or "rgba(67, 160, 71, 0.9)",
            "width": int((line.get("width") if isinstance(line, dict) else 2) or 2),
        },
        "hoverinfo": "skip",
    }


def trace_points(layer: Layer) -> dict[str, Any]:
    feats = [f for f in layer.features if isinstance(f, PointFeature)]
    style = layer.style or {}
    marker = style.get("marker") or {}
    return {
        "type": "scattermapbox",
        "name": layer.title,
        "lon": [p.lon for p in feats],
        "lat": [p.lat for p in feats],
        "mode": "markers",
        "text": [
            str((p.props or {}).get("label") or (p.props or {}).get("name") or "")
            for p in feats
        ],
        "marker": {
            "size": int((marker.get("size") if isinstance(marker, dict) else 6) or 6),
            "color": (marker.get("color") if isinstance(marker, dict) else None)
            or "rgba(255, 193, 7, 0.75)",
        },
        "hovertemplate": "%{text}<extra></extra>",
    }


def trace_point_clusters(layer: Layer, clusters: list[ClusterMarker]) -> dict[str, Any]:
    # Style inherits from the point layer, but with cluster-specific defaults.
    style = layer.style or {}
    marker = style.get("marker") or {}
    color = (
        marker.get("color") if isinstance(marker, dict) else None
    ) or "rgba(255, 193, 7, 0.55)"
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


def selected_points(
    layers: LayerBundle, layer_id: str, ids: set[str]
) -> list[PointFeature]:
    layer = layers.get(layer_id)
    if layer is None or layer.kind != "points":
        return []
    pts = [f for f in layer.features if isinstance(f, PointFeature)]
    return [p for p in pts if _id_matches(p.id, ids)]


def trace_highlight_layer(layers: LayerBundle, highlight: Highlight) -> dict[str, Any]:
    layer = layers.get(highlight.layer_id)
    if layer is None:
        return {
            "type": "scattermapbox",
            "name": highlight.title or "Highlighted",
            "lon": [],
            "lat": [],
        }

    if layer.kind == "points":
        selected = selected_points(layers, highlight.layer_id, highlight.feature_ids)
        return {
            "type": "scattermapbox",
            "name": highlight.title or "Highlighted",
            "lon": [p.lon for p in selected],
            "lat": [p.lat for p in selected],
            "mode": "markers+text",
            "text": [
                str((p.props or {}).get("label") or (p.props or {}).get("name") or "")
                for p in selected
            ],
            "textposition": "top center",
            "marker": {"size": 11, "color": "rgba(229, 57, 53, 0.95)"},
            "hovertemplate": "%{text}<extra></extra>",
        }

    if layer.kind == "lines":
        ids = highlight.feature_ids
        feats = [
            f
            for f in layer.features
            if isinstance(f, LineFeature) and _id_matches(f.id, ids)
        ]
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
        ids = highlight.feature_ids
        feats = [
            f
            for f in layer.features
            if isinstance(f, PolygonFeature) and _id_matches(f.id, ids)
        ]
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

    return {
        "type": "scattermapbox",
        "name": highlight.title or "Highlighted",
        "lon": [],
        "lat": [],
    }
