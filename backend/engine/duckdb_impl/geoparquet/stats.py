from __future__ import annotations

from typing import Any


def base_stats(
    *,
    layer_id: str,
    kind: str,
    view_zoom: float,
    n: int,
    duckdb_ms: float,
    decode_ms: float,
    total_ms: float,
    policy: dict[str, Any] | None = None,
    skipped_reason: str | None = None,
    geom_min_zoom: float | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "layerId": layer_id,
        "kind": kind,
        "source": "geoparquet",
        "zoom": float(view_zoom),
        "n": int(n),
        "duckdbMs": round(float(duckdb_ms), 2),
        "decodeMs": round(float(decode_ms), 2),
        "totalMs": round(float(total_ms), 2),
    }
    if policy is not None:
        out["policy"] = policy
    if skipped_reason:
        out["skippedReason"] = skipped_reason
    if geom_min_zoom is not None:
        out["geomMinZoom"] = float(geom_min_zoom)
    return out

