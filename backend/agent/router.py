from __future__ import annotations

import re
from dataclasses import dataclass

from geo.aoi import BBox
from geo.ops import GeoIndex, distance_to_nearest_station_m, is_point_flooded, transformer_4326_to_32633
from layers.types import PointFeature, PragueLayers
from plotly.build_plot import Highlight


@dataclass(frozen=True)
class AgentResponse:
    """
    What the backend 'agent' decided to do for a prompt.

    - message: natural language explanation (we stream this via append/commit)
    - highlight: optional set of points to emphasize on the map
    """

    message: str
    highlight: Highlight | None = None
    focus_map: bool = False


def route_prompt(prompt: str, layers: PragueLayers, index: GeoIndex, aoi: BBox) -> AgentResponse:
    p = (prompt or "").strip().lower()
    flood_union = index.flood_union_for_aoi(aoi)

    if not p or any(k in p for k in ["show layers", "reset", "start over", "help"]):
        return AgentResponse(
            message=(
                "Loaded Prague layers: Q100 flood extent (polygons), metro tracks (lines), "
                "metro stations/entrances (points), tram tracks (lines), tram stops (points), "
                "and beer POIs (points). Ask things like 'how many pubs are flooded?' or "
                "'recommend 5 safe pubs near metro'."
            )
        )

    if "how many" in p and ("flood" in p or "flooded" in p) and ("pub" in p or "beer" in p):
        flooded, dry = _split_flooded(layers.beer_pois, flood_union)
        return AgentResponse(
            message=f"I found {len(flooded)} beer places in the flood extent and {len(dry)} outside of it."
        )

    if ("dry" in p or "safe" in p) and "metro" in p:
        top_n = _extract_number(p, default=20, clamp=(1, 200))
        ranked = _rank_dry_by_metro_station(
            layers.beer_pois,
            flood_union_4326=flood_union,
            index=index,
            top_n=top_n,
        )
        ids = {pt.id for pt, _ in ranked}
        return AgentResponse(
            message=(
                f"Here are {len(ranked)} dry beer places closest to the nearest metro station "
                "(distance computed in meters using a Prague-friendly projection)."
            ),
            highlight=Highlight(point_ids=ids, title=f"Top {len(ranked)} dry + near metro"),
            focus_map=True,
        )

    if "recommend" in p and ("pub" in p or "beer" in p):
        n = _extract_number(p, default=5, clamp=(1, 25))
        b = aoi.normalized()
        prefer_center = {"lat": (b.min_lat + b.max_lat) / 2.0, "lon": (b.min_lon + b.max_lon) / 2.0}
        ranked = _recommend_safe_pubs(
            layers.beer_pois,
            flood_union_4326=flood_union,
            index=index,
            top_n=n,
            # Interpret "near metro" as near a station/entrance within a radius.
            metro_near_m=300.0,
            tram_near_m=350.0,
            tram_penalty=1.5,
            prefer_center=prefer_center,
        )
        ids = {pt.id for pt, _ in ranked}
        names = [(_label(pt) or pt.id) for pt, _ in ranked]
        bullets = "\n".join([f"- {name}" for name in names])
        return AgentResponse(
            message=f"My {len(ranked)} recommendations (dry + near metro):\n{bullets}",
            highlight=Highlight(point_ids=ids, title=f"Recommended {len(ranked)}"),
            focus_map=True,
        )

    return AgentResponse(
        message=(
            "I didn't recognize that prompt yet. Try: 'how many pubs are flooded?', "
            "'find dry pubs near metro', or 'recommend 5 safe pubs'."
        )
    )


def _split_flooded(
    points: list[PointFeature],
    flood_union_4326,
) -> tuple[list[PointFeature], list[PointFeature]]:
    flooded: list[PointFeature] = []
    dry: list[PointFeature] = []
    for pt in points:
        (flooded if is_point_flooded(pt, flood_union_4326) else dry).append(pt)
    return flooded, dry


def _rank_dry_by_metro_station(
    points: list[PointFeature],
    *,
    flood_union_4326,
    index: GeoIndex,
    top_n: int,
) -> list[tuple[PointFeature, float]]:
    _, dry = _split_flooded(points, flood_union_4326)
    scored = [
        (
            pt,
            distance_to_nearest_station_m(
                pt,
                station_tree_32633=index.metro_station_tree_32633,
                station_points_32633=index.metro_station_points_32633,
            ),
        )
        for pt in dry
    ]
    scored.sort(key=lambda x: x[1])
    return scored[:top_n]


def _recommend_safe_pubs(
    points: list[PointFeature],
    *,
    flood_union_4326,
    index: GeoIndex,
    top_n: int,
    metro_near_m: float,
    tram_near_m: float,
    tram_penalty: float,
    prefer_center: dict[str, float],
) -> list[tuple[PointFeature, float]]:
    """
    Recommend \"safe\" pubs inside the current AOI in a way that feels natural.

    We still require \"near metro\", but we interpret it as \"within near_m meters\".
    Within that band, we prefer pubs closer to the user's current viewport center
    (so recommendations stay local and don't force zooming out).
    """
    _, dry = _split_flooded(points, flood_union_4326)

    metro_scored = [
        (
            pt,
            distance_to_nearest_station_m(
                pt,
                station_tree_32633=index.metro_station_tree_32633,
                station_points_32633=index.metro_station_points_32633,
            ),
        )
        for pt in dry
    ]
    near_metro = [(pt, d) for pt, d in metro_scored if d <= metro_near_m]

    cx, cy = _project_4326_to_32633(prefer_center["lon"], prefer_center["lat"])

    def local_key(pt: PointFeature) -> tuple[float, str]:
        return (_dist_to_center_m(pt, cx, cy), pt.id)

    # Prefer metro: pick local pubs within the station-radius band.
    near_metro.sort(key=lambda x: (local_key(x[0]), x[1]))
    selected: list[tuple[PointFeature, float]] = near_metro[:top_n]
    if len(selected) >= top_n:
        return selected

    # Fill remainder from tram stops (fallback) if present.
    selected_ids = {pt.id for pt, _ in selected}
    if index.tram_stop_points_32633:
        tram_scored: list[tuple[PointFeature, float]] = []
        for pt in dry:
            if pt.id in selected_ids:
                continue
            d_tram = distance_to_nearest_station_m(
                pt,
                station_tree_32633=index.tram_stop_tree_32633,
                station_points_32633=index.tram_stop_points_32633,
            )
            if d_tram <= tram_near_m:
                tram_scored.append((pt, float(d_tram)))

        tram_scored.sort(
            key=lambda x: (float(x[1]) * float(tram_penalty), local_key(x[0]), x[0].id)
        )
        for pt, d in tram_scored:
            if len(selected) >= top_n:
                break
            selected.append((pt, d))
            selected_ids.add(pt.id)

        if len(selected) >= top_n:
            return selected

    # If still short, fall back to closest-to-metro-station ranking.
    metro_scored.sort(key=lambda x: (x[1], x[0].id))
    for pt, d in metro_scored:
        if pt.id in selected_ids:
            continue
        selected.append((pt, d))
        if len(selected) >= top_n:
            break

    return selected[:top_n]


def _project_4326_to_32633(lon: float, lat: float) -> tuple[float, float]:
    t = transformer_4326_to_32633()
    x, y = t.transform(float(lon), float(lat))
    return float(x), float(y)


def _dist_to_center_m(pt: PointFeature, cx: float, cy: float) -> float:
    x, y = _project_4326_to_32633(pt.lon, pt.lat)
    dx = x - cx
    dy = y - cy
    return float((dx * dx + dy * dy) ** 0.5)


def _extract_number(text: str, default: int, clamp: tuple[int, int]) -> int:
    m = re.search(r"\\b(\\d{1,3})\\b", text)
    n = int(m.group(1)) if m else default
    lo, hi = clamp
    return max(lo, min(hi, n))


def _label(pt: PointFeature) -> str | None:
    return pt.props.get("label") or pt.props.get("name")

