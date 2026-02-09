from __future__ import annotations

from typing import Any


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


def order_by(policy: Any, *, bbox: dict[str, str]) -> str:
    """
    Render-policy ordering expression for candidate selection.

    Default: prefer large bbox diagonal (cheap importance proxy without geometry decoding).
    """
    if not isinstance(policy, dict):
        policy = {}
    raw = policy.get("orderBy")
    if isinstance(raw, str) and raw.strip():
        return str(raw).strip()
    dx = f"CAST({bbox['xmax']} AS DOUBLE) - CAST({bbox['xmin']} AS DOUBLE)"
    dy = f"CAST({bbox['ymax']} AS DOUBLE) - CAST({bbox['ymin']} AS DOUBLE)"
    return f"({dx}*{dx} + {dy}*{dy}) DESC"
