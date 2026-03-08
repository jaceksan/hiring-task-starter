from __future__ import annotations

from typing import Any, Literal

InspectMode = Literal["auto", "places", "flood_zones", "roads"]


def parse_request_inspect_mode(request_context: dict[str, Any] | None) -> InspectMode:
    if not isinstance(request_context, dict):
        return "auto"
    raw = str(request_context.get("inspectMode") or "").strip().lower()
    if raw in {"places", "place"}:
        return "places"
    if raw in {"flood_zones", "flood", "floodzones", "flood-zones"}:
        return "flood_zones"
    if raw in {"roads", "road"}:
        return "roads"
    return "auto"
