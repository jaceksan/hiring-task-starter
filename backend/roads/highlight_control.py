from __future__ import annotations

from typing import Any

from layers.types import Layer, LineFeature
from plotly.types import Highlight

ROAD_HIGHLIGHT_MAX_VERTICES = 60_000
ROAD_TYPES: tuple[str, ...] = (
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
)

_TYPE_FCLASSES: dict[str, set[str]] = {
    "motorway": {"motorway", "motorway_link"},
    "trunk": {"trunk", "trunk_link"},
    "primary": {"primary"},
    "secondary": {"secondary"},
    "tertiary": {"tertiary"},
}

_ALIASES: dict[str, str] = {
    "motorway": "motorway",
    "motorways": "motorway",
    "trunk": "trunk",
    "trunks": "trunk",
    "primary": "primary",
    "secondary": "secondary",
    "tertiary": "tertiary",
}


def normalize_road_types(raw_types: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_types or []:
        key = _ALIASES.get(str(raw or "").strip().lower())
        if key is None or key in seen:
            continue
        seen.add(key)
        out.append(key)
    # Keep stable canonical ordering in API responses.
    return [t for t in ROAD_TYPES if t in seen]


def build_road_type_highlights(
    *,
    roads_layer: Layer | None,
    selected_types: list[str],
    source_cap_reached: bool,
    max_vertices: int = ROAD_HIGHLIGHT_MAX_VERTICES,
) -> tuple[list[Highlight], dict[str, Any]]:
    status: dict[str, Any] = {
        "selectedTypes": list(selected_types),
        "visibleTypes": [],
        "hiddenTypes": [],
        "hiddenReasonByType": {},
        "countsByType": {},
        "maxVertices": int(max_vertices),
    }
    if roads_layer is None or roads_layer.kind != "lines" or not selected_types:
        return [], status

    highlights: list[Highlight] = []
    for road_type in selected_types:
        allow_fclass = _TYPE_FCLASSES.get(road_type, set())
        matches = [
            f
            for f in roads_layer.features
            if isinstance(f, LineFeature)
            and str((f.props or {}).get("fclass") or "").lower() in allow_fclass
            and f.id
        ]
        count = len(matches)
        status["countsByType"][road_type] = count
        if count == 0:
            status["hiddenTypes"].append(road_type)
            status["hiddenReasonByType"][road_type] = "noneInView"
            continue

        if source_cap_reached:
            status["hiddenTypes"].append(road_type)
            status["hiddenReasonByType"][road_type] = "sourceCapped"
            continue

        vertices = sum(len(f.coords) for f in matches)
        if vertices > int(max_vertices):
            status["hiddenTypes"].append(road_type)
            status["hiddenReasonByType"][road_type] = "tooDense"
            continue

        status["visibleTypes"].append(road_type)
        title = (
            "Motorways"
            if road_type == "motorway"
            else ("Trunks" if road_type == "trunk" else f"{road_type.title()} roads")
        )
        highlights.append(
            Highlight(
                layer_id=roads_layer.id,
                feature_ids={f.id for f in matches},
                title=title,
                mode="road_filter",
            )
        )

    return highlights, status
