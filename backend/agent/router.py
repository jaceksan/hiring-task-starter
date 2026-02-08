from __future__ import annotations

import re
from dataclasses import dataclass

from geo.ops import GeoIndex, distance_to_metro_m, is_point_flooded
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


def route_prompt(prompt: str, layers: PragueLayers, index: GeoIndex) -> AgentResponse:
    p = (prompt or "").strip().lower()

    if not p or any(k in p for k in ["show layers", "reset", "start over", "help"]):
        return AgentResponse(
            message=(
                "Loaded three layers for Prague: Q100 flood extent (polygons), metro tracks (lines), "
                "and beer POIs (points). Ask things like 'how many pubs are flooded?' or "
                "'recommend 5 safe pubs near metro'."
            )
        )

    if "how many" in p and ("flood" in p or "flooded" in p) and ("pub" in p or "beer" in p):
        flooded, dry = _split_flooded(layers.beer_pois, index)
        return AgentResponse(
            message=f"I found {len(flooded)} beer places in the flood extent and {len(dry)} outside of it."
        )

    if ("dry" in p or "safe" in p) and "metro" in p:
        top_n = _extract_number(p, default=20, clamp=(1, 200))
        ranked = _rank_dry_by_metro(layers.beer_pois, index, top_n=top_n)
        ids = {pt.id for pt, _ in ranked}
        return AgentResponse(
            message=(
                f"Here are {len(ranked)} dry beer places closest to the metro (distance computed in meters "
                "using a Prague-friendly projection)."
            ),
            highlight=Highlight(point_ids=ids, title=f"Top {len(ranked)} dry + near metro"),
        )

    if "recommend" in p and ("pub" in p or "beer" in p):
        n = _extract_number(p, default=5, clamp=(1, 25))
        ranked = _rank_dry_by_metro(layers.beer_pois, index, top_n=n)
        ids = {pt.id for pt, _ in ranked}
        names = [(_label(pt) or pt.id) for pt, _ in ranked]
        bullets = "\n".join([f"- {name}" for name in names])
        return AgentResponse(
            message=f"My {len(ranked)} recommendations (dry + near metro):\n{bullets}",
            highlight=Highlight(point_ids=ids, title=f"Recommended {len(ranked)}"),
        )

    return AgentResponse(
        message=(
            "I didn't recognize that prompt yet. Try: 'how many pubs are flooded?', "
            "'find dry pubs near metro', or 'recommend 5 safe pubs'."
        )
    )


def _split_flooded(points: list[PointFeature], index: GeoIndex) -> tuple[list[PointFeature], list[PointFeature]]:
    flooded: list[PointFeature] = []
    dry: list[PointFeature] = []
    for pt in points:
        (flooded if is_point_flooded(pt, index.flood_union_4326) else dry).append(pt)
    return flooded, dry


def _rank_dry_by_metro(points: list[PointFeature], index: GeoIndex, top_n: int) -> list[tuple[PointFeature, float]]:
    _, dry = _split_flooded(points, index)
    scored = [(pt, distance_to_metro_m(pt, index.metro_union_32633)) for pt in dry]
    scored.sort(key=lambda x: x[1])
    return scored[:top_n]


def _extract_number(text: str, default: int, clamp: tuple[int, int]) -> int:
    m = re.search(r"\\b(\\d{1,3})\\b", text)
    n = int(m.group(1)) if m else default
    lo, hi = clamp
    return max(lo, min(hi, n))


def _label(pt: PointFeature) -> str | None:
    return pt.props.get("label") or pt.props.get("name")

