from __future__ import annotations

import json
from typing import Any

from shapely.wkb import loads as wkb_loads

from layers.types import LineFeature, PointFeature, PolygonFeature


def _load_extra_props(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items()}
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
        except Exception:
            return {}
        return (
            {str(k): v for k, v in parsed.items()} if isinstance(parsed, dict) else {}
        )
    return {}


def decode_point_rows(rows: list[tuple]) -> list[PointFeature]:
    feats: list[PointFeature] = []
    for row in rows:
        if len(row) < 5:
            continue
        fid, lon, lat, name, fclass = row[:5]
        extra_props = _load_extra_props(row[5] if len(row) > 5 else None)
        props: dict[str, Any] = dict(extra_props)
        if name:
            props["name"] = str(name)
            props["label"] = str(name)
        if fclass:
            props["fclass"] = str(fclass)
        feats.append(
            PointFeature(id=str(fid), lon=float(lon), lat=float(lat), props=props)
        )
    return feats


def _props(name: Any, fclass: Any, extra_props: Any | None = None) -> dict[str, Any]:
    props: dict[str, Any] = _load_extra_props(extra_props)
    if name:
        props["name"] = str(name)
    if fclass:
        props["fclass"] = str(fclass)
    return props


def decode_line_rows(rows: list[tuple]) -> list[LineFeature]:
    feats: list[LineFeature] = []
    for row in rows:
        if len(row) < 4:
            continue
        fid, geom_wkb, name, fclass = row[:4]
        extra_props = row[4] if len(row) > 4 else None
        try:
            geom = wkb_loads(bytes(geom_wkb)) if geom_wkb is not None else None
        except Exception:
            geom = None
        if geom is None:
            continue

        props = _props(name, fclass, extra_props)
        if geom.geom_type == "LineString":
            coords = [(float(x), float(y)) for x, y in geom.coords]
            if len(coords) >= 2:
                feats.append(LineFeature(id=str(fid), coords=coords, props=props))
        elif geom.geom_type == "MultiLineString":
            for i, part in enumerate(getattr(geom, "geoms", []) or []):
                coords = [(float(x), float(y)) for x, y in part.coords]
                if len(coords) >= 2:
                    feats.append(
                        LineFeature(id=f"{fid}:{i}", coords=coords, props=props)
                    )
    return feats


def decode_polygon_rows(rows: list[tuple]) -> list[PolygonFeature]:
    feats2: list[PolygonFeature] = []

    def _poly_to_feature(pid: str, poly, props: dict[str, Any]) -> None:
        try:
            ext = [(float(x), float(y)) for x, y in poly.exterior.coords]
        except Exception:
            return
        if len(ext) < 4:
            return
        feats2.append(PolygonFeature(id=pid, rings=[ext], props=props))

    for row in rows:
        if len(row) < 4:
            continue
        fid, geom_wkb, name, fclass = row[:4]
        extra_props = row[4] if len(row) > 4 else None
        try:
            geom = wkb_loads(bytes(geom_wkb)) if geom_wkb is not None else None
        except Exception:
            geom = None
        if geom is None:
            continue

        props = _props(name, fclass, extra_props)
        if geom.geom_type == "Polygon":
            _poly_to_feature(str(fid), geom, props)
        elif geom.geom_type == "MultiPolygon":
            for i, part in enumerate(getattr(geom, "geoms", []) or []):
                _poly_to_feature(f"{fid}:{i}", part, props)

    return feats2
