from __future__ import annotations

from typing import Any, Literal

from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from layers.types import Layer, LayerBundle, PolygonFeature

FloodRiskLevel = Literal["extreme", "very_high", "high", "medium", "low", "any"]


def parse_request_flood_context(
    request_context: dict[str, Any] | None,
) -> tuple[FloodRiskLevel, set[str]]:
    raw_level = (
        request_context.get("floodRiskLevel")
        if isinstance(request_context, dict)
        else None
    )
    level = str(raw_level or "any").strip().lower()
    if level not in {"extreme", "very_high", "high", "medium", "low", "any"}:
        level = "any"

    raw_selected = (
        request_context.get("selectedFloodZoneIds")
        if isinstance(request_context, dict)
        else None
    )
    selected_ids = (
        set(
            str(x).strip()
            for x in raw_selected
            if isinstance(x, str) and str(x).strip()
        )
        if isinstance(raw_selected, list)
        else set()
    )
    return level, selected_ids


def _risk_bucket_from_raw(value: Any) -> str | None:
    if value is None:
        return None
    v = str(value).strip().lower()
    if not v:
        return None
    if v in {"extreme", "q5", "5y", "5"}:
        return "extreme"
    if v in {"very_high", "q20", "20y", "20"}:
        return "very_high"
    if v in {"high", "q100", "100y", "100"}:
        return "high"
    if v in {"medium", "q50", "50y", "50"}:
        return "medium"
    if v in {"low", "any"}:
        return "low"
    return None


def _feature_matches_risk(
    feature: PolygonFeature, *, layer: Layer, flood_risk_level: FloodRiskLevel
) -> bool:
    if flood_risk_level == "any":
        return True

    flood_meta = (
        (layer.metadata or {}).get("floodRisk")
        if isinstance(layer.metadata, dict)
        else None
    )
    risk_property = (
        str((flood_meta or {}).get("property")).strip()
        if isinstance(flood_meta, dict) and (flood_meta or {}).get("property")
        else "flood_risk_level"
    )
    raw = (feature.props or {}).get(risk_property)
    bucket = _risk_bucket_from_raw(raw)
    if bucket is None:
        return False
    return bucket == flood_risk_level


def active_flood_zone_features(
    layer: Layer | None,
    *,
    flood_risk_level: FloodRiskLevel,
    selected_zone_ids: set[str],
) -> list[PolygonFeature]:
    if layer is None or layer.kind != "polygons":
        return []

    feats = [f for f in layer.features if isinstance(f, PolygonFeature)]
    if selected_zone_ids:
        feats = [f for f in feats if f.id in selected_zone_ids]

    return [
        f
        for f in feats
        if _feature_matches_risk(f, layer=layer, flood_risk_level=flood_risk_level)
    ]


def union_from_polygons(features: list[PolygonFeature]) -> Polygon | MultiPolygon:
    polys: list[Polygon] = []
    for f in features:
        if not f.rings:
            continue
        ring = f.rings[0]
        if not ring:
            continue
        try:
            poly = Polygon(ring)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_empty:
                polys.append(poly)
        except Exception:
            continue
    if not polys:
        return Polygon()
    u = unary_union(polys)
    return u.buffer(0) if hasattr(u, "buffer") else u


def filter_flood_layer_for_request(
    layers: LayerBundle,
    *,
    layer_id: str | None,
    flood_risk_level: FloodRiskLevel,
    selected_zone_ids: set[str],
) -> tuple[LayerBundle, dict[str, Any], list[PolygonFeature]]:
    if not layer_id:
        return (
            layers,
            {
                "mode": "selected" if selected_zone_ids else "aoi",
                "riskLevel": flood_risk_level,
                "selectedCount": len(selected_zone_ids),
                "activeZoneCount": 0,
            },
            [],
        )
    layer = layers.get(layer_id)
    if layer is None or layer.kind != "polygons":
        return (
            layers,
            {
                "mode": "selected" if selected_zone_ids else "aoi",
                "riskLevel": flood_risk_level,
                "selectedCount": len(selected_zone_ids),
                "activeZoneCount": 0,
            },
            [],
        )
    active = active_flood_zone_features(
        layer,
        flood_risk_level=flood_risk_level,
        selected_zone_ids=selected_zone_ids,
    )
    filtered_layer = Layer(
        id=layer.id,
        kind=layer.kind,
        title=layer.title,
        features=active,
        style=layer.style,
        metadata=layer.metadata,
    )
    next_layers = LayerBundle(
        layers=[filtered_layer if l.id == layer.id else l for l in layers.layers]
    )
    return (
        next_layers,
        {
            "mode": "selected" if selected_zone_ids else "aoi",
            "riskLevel": flood_risk_level,
            "selectedCount": len(selected_zone_ids),
            "activeZoneCount": len(active),
        },
        active,
    )
