from __future__ import annotations

import re
from dataclasses import dataclass

from shapely.geometry import LineString, Point

from geo.aoi import BBox
from geo.index import GeoIndex, is_point_in_union, transformer_4326_to_3857
from layers.types import LayerBundle, LineFeature, PointFeature
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
) -> AgentResponse:
    p = (prompt or "").strip().lower()

    if not p or any(k in p for k in routing.showLayersKeywords):
        titles = [f"- {layer.title} ({layer.kind})" for layer in layers.layers]
        return AgentResponse(message="Loaded layers:\n" + "\n".join(titles))

    for rule in routing.highlightRules:
        if rule.keywords and any(k.lower() in p for k in rule.keywords):
            return _apply_highlight_rule(
                layers, index=index, aoi=aoi, routing=routing, rule=rule
            )

    if any(k in p for k in {"escape road", "escape roads"}):
        return _escape_roads_for_flooded_places(
            layers, index=index, aoi=aoi, routing=routing
        )

    point_kw = {routing.pointLabelSingular.lower(), routing.pointLabelPlural.lower()}
    mentions_points = any(k and k in p for k in point_kw)

    if (
        any(k in p for k in routing.countKeywords)
        and any(k in p for k in routing.maskKeywords)
        and mentions_points
    ):
        return _count_points_in_mask(layers, index=index, aoi=aoi, routing=routing)

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
            f"- recommend 5 {routing.pointLabelPlural}\n"
        )
    )


def _count_points_in_mask(
    layers: LayerBundle, *, index: GeoIndex, aoi: BBox, routing: ScenarioRouting
) -> AgentResponse:
    pts_layer = layers.get(routing.primaryPointsLayerId)
    if pts_layer is None or pts_layer.kind != "points":
        return AgentResponse(
            message="This scenario has no configured primary point layer."
        )
    pts = [f for f in pts_layer.features if isinstance(f, PointFeature)]

    if not routing.maskPolygonsLayerId:
        return AgentResponse(message=f"I found {len(pts)} {routing.pointLabelPlural}.")

    u = index.polygon_union_for_aoi(routing.maskPolygonsLayerId, aoi)
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


def _escape_roads_for_flooded_places(
    layers: LayerBundle,
    *,
    index: GeoIndex,
    aoi: BBox,
    routing: ScenarioRouting,
) -> AgentResponse:
    pts_layer = layers.get(routing.primaryPointsLayerId)
    if pts_layer is None or pts_layer.kind != "points":
        return AgentResponse(message="This scenario has no configured places layer.")
    roads_layer = next(
        (
            layer
            for layer in layers.layers
            if layer.kind == "lines" and "road" in layer.id
        ),
        None,
    ) or next((layer for layer in layers.layers if layer.kind == "lines"), None)
    if roads_layer is None:
        return AgentResponse(message="This scenario has no road layer to highlight.")
    if not routing.maskPolygonsLayerId:
        return AgentResponse(message="This scenario has no flood mask configured.")

    flood_union = index.polygon_union_for_aoi(routing.maskPolygonsLayerId, aoi)
    flooded_points = [
        p
        for p in pts_layer.features
        if isinstance(p, PointFeature) and is_point_in_union(p, flood_union)
    ]
    if not flooded_points:
        return AgentResponse(
            message=(
                "Flooded places: matched 0, rendering 0. "
                "No flooded places are visible in the current map view."
            )
        )

    flooded_ids_all = [p.id for p in flooded_points if p.id]
    flooded_ids = flooded_ids_all[:500]
    if not flooded_ids:
        return AgentResponse(
            message="I could not resolve flooded place IDs in this view."
        )

    t = transformer_4326_to_3857()
    flooded_m = [Point(*t.transform(p.lon, p.lat)) for p in flooded_points]
    road_candidates = [
        r
        for r in roads_layer.features
        if isinstance(r, LineFeature) and len(r.coords) >= 2 and r.id
    ]
    dry_candidates: list[LineFeature] = []
    for r in road_candidates:
        try:
            line = LineString(r.coords)
            if line.is_empty or line.intersects(flood_union):
                continue
            dry_candidates.append(r)
        except Exception:
            continue
    use_candidates = dry_candidates if dry_candidates else road_candidates

    scored: list[tuple[float, LineFeature]] = []
    for r in use_candidates:
        try:
            line_m = LineString([t.transform(lon, lat) for lon, lat in r.coords])
        except Exception:
            continue
        d = min((line_m.distance(p) for p in flooded_m), default=float("inf"))
        if d != float("inf"):
            scored.append((float(d), r))
    scored.sort(key=lambda row: (row[0], row[1].id))

    roads_ids_all = [r.id for _, r in scored]
    roads_ids = roads_ids_all[:300]
    flooded_h = Highlight(
        layer_id=pts_layer.id,
        feature_ids=set(flooded_ids),
        title="Flooded places",
        mode="prompt",
    )
    roads_h = Highlight(
        layer_id=roads_layer.id,
        feature_ids=set(roads_ids),
        title="Escape roads",
        mode="prompt",
    )
    msg = (
        f"Flooded places: matched {len(flooded_ids_all)}, rendering {len(flooded_ids)} due to budget. "
        f"Escape roads: matched {len(roads_ids_all)}, rendering {len(roads_ids)} due to budget."
    )
    return AgentResponse(
        message=msg,
        highlight=flooded_h,
        highlights=[flooded_h, roads_h],
        focus_map=False,
    )


def _recommend_points(
    layers: LayerBundle,
    *,
    index: GeoIndex,
    aoi: BBox,
    routing: ScenarioRouting,
    top_n: int,
    prefer_center: dict[str, float],
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
        u = index.polygon_union_for_aoi(routing.maskPolygonsLayerId, aoi)
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
