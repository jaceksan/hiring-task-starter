from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from layers.types import LineFeature, PointFeature, PolygonFeature


def load_geojson_polygons(path: Path) -> list[PolygonFeature]:
    data = json.loads(path.read_text(encoding="utf-8"))
    features = data.get("features") or []

    out: list[PolygonFeature] = []
    for i, feature in enumerate(features):
        geom = (feature or {}).get("geometry") or {}
        props = (feature or {}).get("properties") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        if not coords:
            continue

        fid = str((feature or {}).get("id") or props.get("id") or f"poly-{i}")

        if gtype == "Polygon":
            rings = [_to_ring(r) for r in coords]
            if rings:
                out.append(PolygonFeature(id=fid, rings=rings, props=props))
        elif gtype == "MultiPolygon":
            for j, poly in enumerate(coords):
                rings = [_to_ring(r) for r in poly]
                if rings:
                    out.append(
                        PolygonFeature(id=f"{fid}-{j}", rings=rings, props=props)
                    )

    return out


def _to_ring(ring: Any) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in ring or []:
        if not p or len(p) < 2:
            continue
        lon, lat = float(p[0]), float(p[1])
        out.append((lon, lat))
    return out


def load_overpass_points(
    path: Path, *, extra_props: dict[str, Any] | None = None
) -> list[PointFeature]:
    """
    Input: Overpass JSON with `out center;` so:
    - nodes have `lat`/`lon`
    - ways/relations may have `center: {lat, lon}`
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    elements = data.get("elements") or []

    out: list[PointFeature] = []
    for el in elements:
        etype = el.get("type")
        eid = el.get("id")
        tags = el.get("tags") or {}

        lon = el.get("lon")
        lat = el.get("lat")
        if lon is None or lat is None:
            center = el.get("center") or {}
            lon = center.get("lon")
            lat = center.get("lat")

        if lon is None or lat is None:
            continue

        props: dict[str, Any] = {
            "osm_type": etype,
            "osm_id": eid,
            **(extra_props or {}),
            **tags,
        }
        name = tags.get("name")
        if name and "label" not in props:
            props["label"] = name

        out.append(
            PointFeature(
                id=f"{etype}/{eid}", lon=float(lon), lat=float(lat), props=props
            )
        )

    return out


def load_overpass_lines(
    path: Path, *, extra_props: dict[str, Any] | None = None
) -> list[LineFeature]:
    """
    Input: Overpass JSON with `out geom;` for ways, providing `geometry: [{lat,lon}, ...]`.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    elements = data.get("elements") or []

    out: list[LineFeature] = []
    for el in elements:
        if el.get("type") != "way":
            continue

        eid = el.get("id")
        geom = el.get("geometry") or []
        coords: list[tuple[float, float]] = []
        for p in geom:
            lat = p.get("lat")
            lon = p.get("lon")
            if lat is None or lon is None:
                continue
            coords.append((float(lon), float(lat)))

        if len(coords) < 2:
            continue

        props: dict[str, Any] = {
            "osm_type": "way",
            "osm_id": eid,
            **(extra_props or {}),
            **(el.get("tags") or {}),
        }
        out.append(LineFeature(id=f"way/{eid}", coords=coords, props=props))

    return out
