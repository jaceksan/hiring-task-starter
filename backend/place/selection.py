from __future__ import annotations

from typing import Any

from layers.types import Layer, LayerBundle, PointFeature


def parse_request_place_sources(request_context: dict[str, Any] | None) -> set[str]:
    raw = (
        request_context.get("placeSourceTypes")
        if isinstance(request_context, dict)
        else None
    )
    if not isinstance(raw, list):
        return set()
    return {
        str(x).strip().lower() for x in raw if isinstance(x, str) and str(x).strip()
    }


def filter_points_layer_by_source(
    layers: LayerBundle, *, layer_id: str, selected_sources: set[str]
) -> tuple[LayerBundle, dict[str, Any]]:
    layer = layers.get(layer_id)
    if layer is None or layer.kind != "points":
        return layers, {
            "selectedSources": sorted(selected_sources),
            "availableSources": [],
            "activeSources": [],
            "beforeCount": 0,
            "afterCount": 0,
        }

    points = [f for f in layer.features if isinstance(f, PointFeature)]
    available = sorted(
        {
            str((p.props or {}).get("place_source") or "").strip().lower()
            for p in points
            if str((p.props or {}).get("place_source") or "").strip()
        }
    )
    before_count = len(points)
    if not selected_sources:
        return layers, {
            "selectedSources": [],
            "availableSources": available,
            "activeSources": available,
            "beforeCount": before_count,
            "afterCount": before_count,
        }

    active = sorted([s for s in selected_sources if s in set(available)])
    filtered = [
        p
        for p in points
        if str((p.props or {}).get("place_source") or "").strip().lower() in set(active)
    ]
    replacement = Layer(
        id=layer.id,
        kind=layer.kind,
        title=layer.title,
        features=filtered,
        style=layer.style,
        metadata=layer.metadata,
    )
    next_layers = LayerBundle(
        layers=[replacement if l.id == layer.id else l for l in layers.layers]
    )
    return next_layers, {
        "selectedSources": sorted(selected_sources),
        "availableSources": available,
        "activeSources": active,
        "beforeCount": before_count,
        "afterCount": len(filtered),
    }
