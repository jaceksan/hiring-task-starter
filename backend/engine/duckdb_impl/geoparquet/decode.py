from __future__ import annotations

from typing import Any

from shapely.wkb import loads as wkb_loads

from layers.types import LineFeature, PointFeature, PolygonFeature


def decode_point_rows(rows: list[tuple]) -> list[PointFeature]:
    feats: list[PointFeature] = []
    for fid, lon, lat, name, fclass in rows:
        props: dict[str, Any] = {}
        if name:
            props["name"] = str(name)
            props["label"] = str(name)
        if fclass:
            props["fclass"] = str(fclass)
        feats.append(PointFeature(id=str(fid), lon=float(lon), lat=float(lat), props=props))
    return feats


def _props(name, fclass) -> dict[str, Any]:
    props: dict[str, Any] = {}
    if name:
        props["name"] = str(name)
    if fclass:
        props["fclass"] = str(fclass)
    return props


def decode_line_rows(rows: list[tuple]) -> list[LineFeature]:
    feats: list[LineFeature] = []
    for fid, geom_wkb, name, fclass in rows:
        try:
            geom = wkb_loads(bytes(geom_wkb)) if geom_wkb is not None else None
        except Exception:
            geom = None
        if geom is None:
            continue

        props = _props(name, fclass)
        if geom.geom_type == "LineString":
            coords = [(float(x), float(y)) for x, y in geom.coords]
            if len(coords) >= 2:
                feats.append(LineFeature(id=str(fid), coords=coords, props=props))
        elif geom.geom_type == "MultiLineString":
            for i, part in enumerate(getattr(geom, "geoms", []) or []):
                coords = [(float(x), float(y)) for x, y in part.coords]
                if len(coords) >= 2:
                    feats.append(LineFeature(id=f"{fid}:{i}", coords=coords, props=props))
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

    for fid, geom_wkb, name, fclass in rows:
        try:
            geom = wkb_loads(bytes(geom_wkb)) if geom_wkb is not None else None
        except Exception:
            geom = None
        if geom is None:
            continue

        props = _props(name, fclass)
        if geom.geom_type == "Polygon":
            _poly_to_feature(str(fid), geom, props)
        elif geom.geom_type == "MultiPolygon":
            for i, part in enumerate(getattr(geom, "geoms", []) or []):
                _poly_to_feature(f"{fid}:{i}", part, props)

    return feats2

