from __future__ import annotations

from typing import Any

from layers.types import Layer, LayerBundle, PointFeature


def parse_request_place_categories(
    request_context: dict[str, Any] | None,
) -> set[str] | None:
    if not isinstance(request_context, dict):
        return None
    # Backward compatibility: older frontend sent placeSourceTypes.
    if "placeCategories" in request_context:
        raw = request_context.get("placeCategories")
    elif "placeSourceTypes" in request_context:
        raw = request_context.get("placeSourceTypes")
    else:
        return None
    if not isinstance(raw, list):
        return set()
    return {
        str(x).strip().lower() for x in raw if isinstance(x, str) and str(x).strip()
    }


def filter_points_layer_by_category(
    layers: LayerBundle, *, layer_id: str, selected_categories: set[str] | None
) -> tuple[LayerBundle, dict[str, Any]]:
    layer = layers.get(layer_id)
    if layer is None or layer.kind != "points":
        return layers, {
            "selectedCategories": sorted(selected_categories or []),
            "availableCategories": [],
            "activeCategories": [],
            "beforeCount": 0,
            "afterCount": 0,
        }

    points = [f for f in layer.features if isinstance(f, PointFeature)]
    available = sorted(
        {
            str((p.props or {}).get("place_category") or "").strip().lower()
            for p in points
            if str((p.props or {}).get("place_category") or "").strip()
        }
    )
    before_count = len(points)
    if selected_categories is None:
        return layers, {
            "selectedCategories": [],
            "availableCategories": available,
            "activeCategories": available,
            "beforeCount": before_count,
            "afterCount": before_count,
        }
    if not selected_categories:
        replacement = Layer(
            id=layer.id,
            kind=layer.kind,
            title=layer.title,
            features=[],
            style=layer.style,
            metadata=layer.metadata,
        )
        next_layers = LayerBundle(
            layers=[
                replacement if layer_item.id == layer.id else layer_item
                for layer_item in layers.layers
            ]
        )
        return next_layers, {
            "selectedCategories": [],
            "availableCategories": available,
            "activeCategories": [],
            "beforeCount": before_count,
            "afterCount": 0,
        }

    active = sorted([s for s in selected_categories if s in set(available)])
    filtered = [
        p
        for p in points
        if str((p.props or {}).get("place_category") or "").strip().lower()
        in set(active)
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
        layers=[
            replacement if layer_item.id == layer.id else layer_item
            for layer_item in layers.layers
        ]
    )
    return next_layers, {
        "selectedCategories": sorted(selected_categories or []),
        "availableCategories": available,
        "activeCategories": active,
        "beforeCount": before_count,
        "afterCount": len(filtered),
    }
