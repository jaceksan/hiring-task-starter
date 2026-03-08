from __future__ import annotations

from typing import Any

ROAD_CLASS_PRIORITY_GROUPS: list[tuple[str, ...]] = [
    ("motorway", "motorway_link"),
    ("trunk", "trunk_link"),
    ("primary", "primary_link"),
    ("secondary", "secondary_link"),
    ("tertiary", "tertiary_link"),
]


def _as_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _as_int(v: Any) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def choose_by_max_zoom(mapping: Any, zoom: float, *, default: int | None) -> int | None:
    """
    Choose a value from {maxZoom -> value} where maxZoom is an inclusive upper bound.

    Example:
      {7.5: 3000, 9.0: 8000, 20.0: 40000}
    """
    if not isinstance(mapping, dict):
        return default
    items: list[tuple[float, int]] = []
    for k, v in mapping.items():
        kz = _as_float(k)
        iv = _as_int(v)
        if kz is None or iv is None:
            continue
        items.append((float(kz), int(iv)))
    if not items:
        return default
    items.sort(key=lambda t: t[0])
    for max_zoom, value in items:
        if float(zoom) <= float(max_zoom):
            return int(value)
    return int(items[-1][1])


def allowed_classes(policy: Any, zoom: float) -> set[str] | None:
    """
    Return allowed fclass values based on zoom.

    Policy option:
      minZoomForGeometryByClass: {motorway: 6.0, residential: 13.0, ...}
    """
    if not isinstance(policy, dict):
        return None
    m = policy.get("minZoomForGeometryByClass")
    if not isinstance(m, dict):
        return None
    allowed: set[str] = set()
    for cls, min_z in m.items():
        z = _as_float(min_z)
        if z is None:
            continue
        if float(zoom) >= float(z):
            allowed.add(str(cls))
    return allowed or None


def order_by(policy: Any, *, bbox: dict[str, str]) -> str | None:
    """
    Render-policy ordering expression for candidate selection.

    Default: no ordering for performance.
    (Ordering forces a sort over large candidate sets; prefer tight caps instead.)
    """
    if not isinstance(policy, dict):
        policy = {}
    raw = policy.get("orderBy")
    if isinstance(raw, str) and raw.strip():
        return str(raw).strip()
    return None


def prioritize_road_classes(classes: set[str]) -> list[tuple[str, ...]]:
    out: list[tuple[str, ...]] = []
    remaining = {str(c).strip() for c in classes if str(c).strip()}
    for group in ROAD_CLASS_PRIORITY_GROUPS:
        picked = tuple(c for c in group if c in remaining)
        if not picked:
            continue
        out.append(picked)
        remaining.difference_update(picked)
    if remaining:
        out.append(tuple(sorted(remaining)))
    return out


def choose_road_classes_by_budget(
    *,
    class_counts: dict[str, int],
    allowed_classes: set[str] | None,
    cap: int,
) -> tuple[set[str] | None, dict[str, Any]]:
    if not allowed_classes:
        return None, {
            "enabled": False,
            "cap": int(cap),
            "admittedClasses": [],
            "rejectedAtClass": None,
            "cumulativeAtCutoff": 0,
            "classCounts": {},
            "oversizedFirstGroup": False,
        }

    cleaned_counts = {
        str(k): max(0, int(v or 0))
        for k, v in class_counts.items()
        if str(k) in allowed_classes
    }
    groups = prioritize_road_classes(set(allowed_classes))
    admitted: set[str] = set()
    cumulative = 0
    rejected_at: str | None = None
    oversized_first = False

    for group in groups:
        group_count = sum(cleaned_counts.get(c, 0) for c in group)
        if group_count <= 0:
            continue
        if cumulative == 0 and group_count > int(cap):
            admitted.update(group)
            cumulative += int(group_count)
            oversized_first = True
            rejected_at = group[0]
            break
        if cumulative + group_count <= int(cap):
            admitted.update(group)
            cumulative += int(group_count)
            continue
        rejected_at = group[0]
        break

    return admitted, {
        "enabled": True,
        "cap": int(cap),
        "admittedClasses": sorted(admitted),
        "rejectedAtClass": rejected_at,
        "cumulativeAtCutoff": int(cumulative),
        "classCounts": {k: int(v) for k, v in sorted(cleaned_counts.items())},
        "oversizedFirstGroup": bool(oversized_first),
    }
