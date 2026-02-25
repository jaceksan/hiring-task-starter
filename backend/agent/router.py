from __future__ import annotations

import re
from dataclasses import dataclass

from shapely.geometry import LineString, Point

from flood.selection import (
    FloodRiskLevel,
    active_flood_zone_features,
    parse_request_flood_context,
    union_from_polygons,
)
from geo.aoi import BBox
from geo.index import GeoIndex, is_point_in_union, transformer_4326_to_3857
from layers.types import Layer, LayerBundle, LineFeature, PointFeature
from plotly.build_map import Highlight
from scenarios.types import ScenarioHighlightRule, ScenarioRouting


@dataclass(frozen=True)
class AgentResponse:
    """
    What the backend 'agent' decided to do for a prompt.

    - message: natural language explanation (we stream this via append/commit)
    - highlight: optional set of points to emphasize on the map
    """

    message: str
    highlight: Highlight | None = None
    highlights: list[Highlight] | None = None
    focus_map: bool = False


def route_prompt(
    prompt: str,
    *,
    layers: LayerBundle,
    index: GeoIndex,
    aoi: BBox,
    routing: ScenarioRouting,
    view_center: dict[str, float] | None = None,
    request_context: dict | None = None,
) -> AgentResponse:
    p = (prompt or "").strip().lower()
    flood_risk_level, selected_zone_ids = parse_request_flood_context(request_context)

    if not p or any(k in p for k in routing.showLayersKeywords):
        titles = [f"- {layer.title} ({layer.kind})" for layer in layers.layers]
        return AgentResponse(message="Loaded layers:\n" + "\n".join(titles))

    if _is_escape_roads_prompt(p):
        return _escape_roads_for_flooded_places(
            layers,
            aoi=aoi,
            routing=routing,
            flood_risk_level=flood_risk_level,
            selected_zone_ids=selected_zone_ids,
        )

    if _is_safest_prompt(p):
        n = _extract_number(p, default=5, clamp=(1, 20))
        b = aoi.normalized()
        prefer_center = view_center or {
            "lat": (b.min_lat + b.max_lat) / 2.0,
            "lon": (b.min_lon + b.max_lon) / 2.0,
        }
        return _safest_places_with_reachable_roads(
            layers,
            routing=routing,
            top_n=n,
            prefer_center=prefer_center,
            flood_risk_level=flood_risk_level,
            selected_zone_ids=selected_zone_ids,
        )

    for rule in routing.highlightRules:
        if rule.keywords and any(k.lower() in p for k in rule.keywords):
            return _apply_highlight_rule(
                layers, index=index, aoi=aoi, routing=routing, rule=rule
            )

    point_kw = {routing.pointLabelSingular.lower(), routing.pointLabelPlural.lower()}
    mentions_points = any(k and k in p for k in point_kw)

    if (
        any(k in p for k in routing.countKeywords)
        and any(k in p for k in routing.maskKeywords)
        and mentions_points
    ):
        return _count_points_in_mask(
            layers,
            index=index,
            aoi=aoi,
            routing=routing,
            flood_risk_level=flood_risk_level,
            selected_zone_ids=selected_zone_ids,
        )

    if any(k in p for k in routing.recommendKeywords) and mentions_points:
        n = _extract_number(p, default=5, clamp=(1, 50))
        b = aoi.normalized()
        prefer_center = view_center or {
            "lat": (b.min_lat + b.max_lat) / 2.0,
            "lon": (b.min_lon + b.max_lon) / 2.0,
        }
        ranked = _recommend_points(
            layers,
            index=index,
            aoi=aoi,
            routing=routing,
            top_n=n,
            prefer_center=prefer_center,
            flood_risk_level=flood_risk_level,
            selected_zone_ids=selected_zone_ids,
        )
        ids = {pt.id for pt, _ in ranked}
        bullets = "\n".join([f"- {(_label(pt) or pt.id)}" for pt, _ in ranked])
        return AgentResponse(
            message=f"My {len(ranked)} recommendations:\n{bullets}",
            highlight=Highlight(
                layer_id=routing.primaryPointsLayerId,
                feature_ids=ids,
                title=f"Recommended {len(ranked)}",
                mode="prompt",
            ),
            highlights=[
                Highlight(
                    layer_id=routing.primaryPointsLayerId,
                    feature_ids=ids,
                    title=f"Recommended {len(ranked)}",
                    mode="prompt",
                )
            ],
            focus_map=True,
        )

    # Fallback help.
    return AgentResponse(
        message=(
            "I didn't recognize that prompt yet. Try:\n"
            f"- show layers\n"
            f"- how many {routing.pointLabelPlural} are flooded?\n"
            "- show me escape roads for places in flood zone\n"
            "- show safest nearby places outside selected flood risk with reachable roads\n"
        )
    )


def _count_points_in_mask(
    layers: LayerBundle,
    *,
    index: GeoIndex,
    aoi: BBox,
    routing: ScenarioRouting,
    flood_risk_level: FloodRiskLevel,
    selected_zone_ids: set[str],
) -> AgentResponse:
    pts_layer = layers.get(routing.primaryPointsLayerId)
    if pts_layer is None or pts_layer.kind != "points":
        return AgentResponse(
            message="This scenario has no configured primary point layer."
        )
    pts = [f for f in pts_layer.features if isinstance(f, PointFeature)]

    if not routing.maskPolygonsLayerId:
        return AgentResponse(message=f"I found {len(pts)} {routing.pointLabelPlural}.")

    mask_layer = layers.get(routing.maskPolygonsLayerId)
    active_zones = active_flood_zone_features(
        mask_layer,
        flood_risk_level=flood_risk_level,
        selected_zone_ids=selected_zone_ids,
    )
    u = union_from_polygons(active_zones)
    in_mask = [pt for pt in pts if is_point_in_union(pt, u)]
    out_mask = [pt for pt in pts if not is_point_in_union(pt, u)]
    return AgentResponse(
        message=(
            f"I found {len(in_mask)} {routing.pointLabelPlural} in {routing.maskLabel} "
            f"and {len(out_mask)} outside of it."
        )
    )


def _apply_highlight_rule(
    layers: LayerBundle,
    *,
    index: GeoIndex,
    aoi: BBox,
    routing: ScenarioRouting,
    rule: ScenarioHighlightRule,
) -> AgentResponse:
    layer = layers.get(rule.layerId)
    if layer is None:
        return AgentResponse(message=f"I couldn't find layer '{rule.layerId}'.")

    feats = layer.features
    feats_before_filters = feats

    # Optional props filter.
    if rule.props:
        filtered = []
        for f in feats:
            props = getattr(f, "props", None) or {}
            ok = True
            for k, allowed in (rule.props or {}).items():
                v = props.get(k)
                if v is None or str(v) not in set(allowed or []):
                    ok = False
                    break
            if ok:
                filtered.append(f)
        feats = filtered

    # Optional mask filter (primarily for points).
    if rule.maskLayerId:
        u = index.polygon_union_for_aoi(rule.maskLayerId, aoi)
        if layer.kind == "points":
            pts = [f for f in feats if isinstance(f, PointFeature)]
            if rule.maskMode == "OUTSIDE_MASK":
                feats = [pt for pt in pts if not is_point_in_union(pt, u)]
            else:
                feats = [pt for pt in pts if is_point_in_union(pt, u)]

    ids_all = [getattr(f, "id", "") for f in feats if getattr(f, "id", "")]
    max_features = int(rule.maxFeatures or 500)
    ids = ids_all[:max_features]
    if not ids:
        # Be helpful: distinguish "layer not loaded at this zoom" vs "filter found none".
        if not feats_before_filters and layer.kind in {"lines", "polygons"}:
            return AgentResponse(
                message=(
                    f"I can’t highlight anything yet because `{layer.title}` has no decoded "
                    f"features at the current zoom. Zoom in a bit (or pan) and try again."
                )
            )

        if rule.props:
            props_bits: list[str] = []
            for k, allowed in (rule.props or {}).items():
                if allowed:
                    props_bits.append(f"{k} ∈ {list(allowed)}")
            props_msg = f" ({', '.join(props_bits)})" if props_bits else ""

            # If the layer has features but none match the props filter, say so explicitly.
            if feats_before_filters:
                # Show a small hint about what classes are present in the current view.
                present: list[str] = []
                try:
                    seen: set[str] = set()
                    for f in feats_before_filters:
                        v = (getattr(f, "props", None) or {}).get("fclass")
                        if v is None:
                            continue
                        s = str(v)
                        if s and s not in seen:
                            seen.add(s)
                            present.append(s)
                        if len(present) >= 6:
                            break
                except Exception:
                    present = []
                present_msg = (
                    f" (present fclass: {', '.join(present)})" if present else ""
                )
                return AgentResponse(
                    message=(
                        f"I can see {len(feats_before_filters)} `{layer.title}` features in the current view, "
                        f"but none match your filter{props_msg}.{present_msg} "
                        "Try panning to a major highway corridor or zooming out slightly and ask again."
                    )
                )

            return AgentResponse(
                message=(
                    f"I couldn’t find any `{layer.title}` matching your request{props_msg} "
                    "in the current map view. Try zooming out a bit (or panning) and ask again."
                )
            )

        return AgentResponse(
            message=(
                "I couldn’t find anything matching that request in your current map view. "
                "Try zooming out a bit (or panning) and ask again."
            )
        )

    title = rule.title or f"Highlighted ({layer.title})"
    # Always state matched vs rendered so budget/cap behavior is explicit.
    clipped_note = (
        f"matched {len(ids_all)}, rendering {len(ids)} due to budget."
        if len(ids_all) > len(ids)
        else f"matched {len(ids_all)}, rendering {len(ids)}."
    )
    msg = f"{layer.title}: {clipped_note}"
    if rule.maskLayerId and rule.maskMode == "IN_MASK":
        msg = f"{layer.title} overlapping {routing.maskLabel}: {clipped_note}"
    if rule.maskLayerId and rule.maskMode == "OUTSIDE_MASK":
        msg = f"{layer.title} outside {routing.maskLabel}: {clipped_note}"
    hl = Highlight(layer_id=layer.id, feature_ids=set(ids), title=title, mode="prompt")
    return AgentResponse(
        message=msg,
        highlight=hl,
        highlights=[hl],
        focus_map=(layer.kind == "points"),
    )


def _recommend_points(
    layers: LayerBundle,
    *,
    index: GeoIndex,
    aoi: BBox,
    routing: ScenarioRouting,
    top_n: int,
    prefer_center: dict[str, float],
    flood_risk_level: FloodRiskLevel,
    selected_zone_ids: set[str],
) -> list[tuple[PointFeature, float]]:
    pts_layer = layers.get(routing.primaryPointsLayerId)
    if pts_layer is None or pts_layer.kind != "points":
        return []
    pts = [f for f in pts_layer.features if isinstance(f, PointFeature)]
    if not pts:
        return []

    # Apply mask if configured.
    candidates = pts
    if routing.maskPolygonsLayerId:
        mask_layer = layers.get(routing.maskPolygonsLayerId)
        active_zones = active_flood_zone_features(
            mask_layer,
            flood_risk_level=flood_risk_level,
            selected_zone_ids=selected_zone_ids,
        )
        u = union_from_polygons(active_zones)
        candidates = [pt for pt in pts if not is_point_in_union(pt, u)]

    if not candidates:
        return []

    cx, cy = transformer_4326_to_3857().transform(
        prefer_center["lon"], prefer_center["lat"]
    )

    def local_key(pt: PointFeature) -> tuple[float, str]:
        x, y = transformer_4326_to_3857().transform(pt.lon, pt.lat)
        dx = float(x) - float(cx)
        dy = float(y) - float(cy)
        return (dx * dx + dy * dy, pt.id)

    # If no proximity rules, just pick local points.
    if not routing.proximity:
        candidates.sort(key=local_key)
        return [(pt, 0.0) for pt in candidates[:top_n]]

    scored: list[tuple[PointFeature, float]] = []
    for pt in candidates:
        best = float("inf")
        for rule in routing.proximity:
            d = index.distance_to_nearest_point_m(pt, point_layer_id=rule.layerId)
            if d <= rule.maxMeters:
                best = min(best, float(d) * float(rule.penalty))
        if best != float("inf"):
            scored.append((pt, best))

    if not scored:
        candidates.sort(key=local_key)
        return [(pt, 0.0) for pt in candidates[:top_n]]

    scored.sort(key=lambda x: (x[1], local_key(x[0])))
    return scored[:top_n]


def _is_escape_roads_prompt(prompt: str) -> bool:
    return (
        "escape" in prompt
        and "road" in prompt
        and ("flood" in prompt or "flood zone" in prompt)
    )


def _is_safest_prompt(prompt: str) -> bool:
    has_safest = "safest" in prompt or ("safe" in prompt and "nearby" in prompt)
    has_roads = "road" in prompt and "reachable" in prompt
    return bool(has_safest and has_roads)


def _roads_layer(layers: LayerBundle) -> Layer | None:
    roads = layers.get("roads")
    if roads is not None and roads.kind == "lines":
        return roads
    return next(
        (layer_item for layer_item in layers.layers if layer_item.kind == "lines"), None
    )


def _projected_road_lines(roads: list[LineFeature]) -> list[tuple[str, LineString]]:
    out: list[tuple[str, LineString]] = []
    for road in roads:
        if len(road.coords) < 2:
            continue
        try:
            out.append(
                (
                    road.id,
                    LineString(
                        [
                            transformer_4326_to_3857().transform(lon, lat)
                            for lon, lat in road.coords
                        ]
                    ),
                )
            )
        except Exception:
            continue
    return out


def _nearest_road(
    point: PointFeature, road_lines: list[tuple[str, LineString]]
) -> tuple[str, float] | None:
    px, py = transformer_4326_to_3857().transform(point.lon, point.lat)
    pt = Point(float(px), float(py))
    best: tuple[str, float] | None = None
    for road_id, line in road_lines:
        d = float(pt.distance(line))
        if best is None or d < best[1]:
            best = (road_id, d)
    return best


def _escape_roads_for_flooded_places(
    layers: LayerBundle,
    *,
    aoi: BBox,
    routing: ScenarioRouting,
    flood_risk_level: FloodRiskLevel,
    selected_zone_ids: set[str],
) -> AgentResponse:
    pts_layer = layers.get(routing.primaryPointsLayerId)
    roads_layer = _roads_layer(layers)
    mask_layer = (
        layers.get(routing.maskPolygonsLayerId) if routing.maskPolygonsLayerId else None
    )
    if pts_layer is None or pts_layer.kind != "points" or roads_layer is None:
        return AgentResponse(
            message="Missing points/roads layers for escape-road analysis."
        )

    active_zones = active_flood_zone_features(
        mask_layer,
        flood_risk_level=flood_risk_level,
        selected_zone_ids=selected_zone_ids,
    )
    if not active_zones:
        return AgentResponse(
            message="No active flood zones match the current filter in this view."
        )
    union = union_from_polygons(active_zones)

    flooded_places = [
        p
        for p in pts_layer.features
        if isinstance(p, PointFeature) and is_point_in_union(p, union)
    ]
    flooded_places = flooded_places[:300]
    roads = [r for r in roads_layer.features if isinstance(r, LineFeature)]
    road_lines = _projected_road_lines(roads)

    escape_road_ids: set[str] = set()
    connected_place_ids: set[str] = set()
    for place in flooded_places:
        nearest = _nearest_road(place, road_lines)
        if nearest is None:
            continue
        road_id, d_m = nearest
        if d_m > 350.0:
            continue
        road = next((r for r in roads if r.id == road_id), None)
        if road is None:
            continue
        if len(road.coords) < 2:
            continue
        try:
            road_line = LineString(road.coords)
            if union.contains(road_line):
                continue
        except Exception:
            pass
        escape_road_ids.add(road_id)
        connected_place_ids.add(place.id)

    if not escape_road_ids:
        return AgentResponse(
            message=(
                f"Found {len(flooded_places)} flooded {routing.pointLabelPlural}, "
                "but no reachable escape roads in the current view."
            )
        )

    place_title = f"Flooded {routing.pointLabelPlural} with escape roads"
    road_title = "Escape roads"
    return AgentResponse(
        message=(
            f"Found {len(connected_place_ids)} flooded {routing.pointLabelPlural} with "
            f"{len(escape_road_ids)} reachable escape roads."
        ),
        highlight=Highlight(
            layer_id=roads_layer.id,
            feature_ids=escape_road_ids,
            title=road_title,
            mode="prompt",
        ),
        highlights=[
            Highlight(
                layer_id=pts_layer.id,
                feature_ids=connected_place_ids,
                title=place_title,
                mode="prompt",
            ),
            Highlight(
                layer_id=roads_layer.id,
                feature_ids=escape_road_ids,
                title=road_title,
                mode="prompt",
            ),
        ],
    )


def _safest_places_with_reachable_roads(
    layers: LayerBundle,
    *,
    routing: ScenarioRouting,
    top_n: int,
    prefer_center: dict[str, float],
    flood_risk_level: FloodRiskLevel,
    selected_zone_ids: set[str],
) -> AgentResponse:
    pts_layer = layers.get(routing.primaryPointsLayerId)
    roads_layer = _roads_layer(layers)
    mask_layer = (
        layers.get(routing.maskPolygonsLayerId) if routing.maskPolygonsLayerId else None
    )
    if pts_layer is None or pts_layer.kind != "points" or roads_layer is None:
        return AgentResponse(
            message="Missing points/roads layers for safety recommendations."
        )

    active_zones = active_flood_zone_features(
        mask_layer,
        flood_risk_level=flood_risk_level,
        selected_zone_ids=selected_zone_ids,
    )
    union = union_from_polygons(active_zones)

    places = [p for p in pts_layer.features if isinstance(p, PointFeature)]
    dry_places = [p for p in places if not is_point_in_union(p, union)]
    if not dry_places:
        return AgentResponse(
            message=f"No {routing.pointLabelPlural} outside active flood zones in this view."
        )

    cx, cy = transformer_4326_to_3857().transform(
        float(prefer_center["lon"]), float(prefer_center["lat"])
    )

    def local_score(pt: PointFeature) -> float:
        x, y = transformer_4326_to_3857().transform(pt.lon, pt.lat)
        dx = float(x) - float(cx)
        dy = float(y) - float(cy)
        return dx * dx + dy * dy

    dry_places.sort(key=local_score)
    candidates = dry_places[:1500]
    roads = [r for r in roads_layer.features if isinstance(r, LineFeature)]
    road_lines = _projected_road_lines(roads)

    scored: list[tuple[PointFeature, float, str]] = []
    for pt in candidates:
        nearest = _nearest_road(pt, road_lines)
        if nearest is None:
            continue
        road_id, d_m = nearest
        if d_m > 350.0:
            continue
        score = local_score(pt) + (d_m * d_m)
        scored.append((pt, score, road_id))

    if not scored:
        return AgentResponse(
            message=(
                f"Couldn’t find nearby {routing.pointLabelPlural} with reachable roads "
                "outside active flood zones."
            )
        )

    scored.sort(key=lambda x: (x[1], x[0].id))
    picked = scored[:top_n]
    place_ids = {pt.id for pt, _, _ in picked}
    road_ids = {rid for _, _, rid in picked}
    bullets = "\n".join([f"- {(_label(pt) or pt.id)}" for pt, _, _ in picked])
    return AgentResponse(
        message=(
            f"Safest nearby {routing.pointLabelPlural} with reachable roads:\n{bullets}"
        ),
        highlight=Highlight(
            layer_id=pts_layer.id,
            feature_ids=place_ids,
            title=f"Safest {len(place_ids)}",
            mode="prompt",
        ),
        highlights=[
            Highlight(
                layer_id=pts_layer.id,
                feature_ids=place_ids,
                title=f"Safest {len(place_ids)}",
                mode="prompt",
            ),
            Highlight(
                layer_id=roads_layer.id,
                feature_ids=road_ids,
                title="Reachable roads",
                mode="prompt",
            ),
        ],
        focus_map=True,
    )


def _label(pt: PointFeature) -> str | None:
    props = pt.props or {}
    return props.get("label") or props.get("name") or None


def _extract_number(prompt: str, *, default: int, clamp: tuple[int, int]) -> int:
    m = re.search(r"(\d+)", prompt)
    if not m:
        return default
    try:
        n = int(m.group(1))
    except Exception:
        return default
    lo, hi = clamp
    return max(lo, min(hi, n))
