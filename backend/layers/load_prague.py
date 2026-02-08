from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .types import LineFeature, PointFeature, PolygonFeature, PragueLayers


def _repo_root() -> Path:
    # .../hiring-task-starter/backend/layers/load_prague.py -> repo root is 2 levels up
    return Path(__file__).resolve().parents[2]


def _data_dir() -> Path:
    return _repo_root() / "data" / "prague"


def load_prague_layers(data_dir: Path | None = None) -> PragueLayers:
    """
    Load the reproducible Prague layers committed under `data/prague/`.

    We keep loaders pure and deterministic so they're easy to swap later.
    """
    base = data_dir or _data_dir()

    flood_q100 = load_flood_q100(base / "prague_q100_flood.geojson")
    beer_pois = load_beer_pois_overpass(base / "prague_beer_pois_overpass.json")
    metro_ways = load_metro_ways_overpass(base / "prague_metro_ways_overpass.json")
    metro_stations = load_metro_stations_overpass(base / "prague_metro_stations_overpass.json")
    tram_ways = load_tram_ways_overpass(base / "prague_tram_ways_overpass.json")
    tram_stops = load_tram_stops_overpass(base / "prague_tram_stops_overpass.json")

    return PragueLayers(
        flood_q100=flood_q100,
        metro_ways=metro_ways,
        metro_stations=metro_stations,
        tram_ways=tram_ways,
        tram_stops=tram_stops,
        beer_pois=beer_pois,
    )


def load_flood_q100(path: Path) -> list[PolygonFeature]:
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

        fid = str((feature or {}).get("id") or props.get("id") or f"flood-{i}")

        if gtype == "Polygon":
            # coords: [ring1, ring2, ...]; each ring is [[lon,lat],...]
            rings = [_to_ring(r) for r in coords]
            if rings:
                out.append(PolygonFeature(id=fid, rings=rings, props=props))
        elif gtype == "MultiPolygon":
            # coords: [polygon1, polygon2, ...]; polygon is [ring1, ring2, ...]
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


def load_beer_pois_overpass(path: Path) -> list[PointFeature]:
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
            **tags,
        }
        name = tags.get("name")
        if name:
            props["label"] = name

        out.append(
            PointFeature(
                id=f"{etype}/{eid}",
                lon=float(lon),
                lat=float(lat),
                props=props,
            )
        )

    return out


def load_metro_stations_overpass(path: Path) -> list[PointFeature]:
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
            "layer_kind": "metro_station",
            **tags,
        }
        name = tags.get("name")
        if name:
            props["label"] = name

        out.append(
            PointFeature(
                id=f"{etype}/{eid}",
                lon=float(lon),
                lat=float(lat),
                props=props,
            )
        )

    return out


def load_metro_ways_overpass(path: Path) -> list[LineFeature]:
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

        props = {
            "osm_type": "way",
            "osm_id": eid,
            **(el.get("tags") or {}),
        }
        out.append(LineFeature(id=f"way/{eid}", coords=coords, props=props))

    return out


def load_tram_ways_overpass(path: Path) -> list[LineFeature]:
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

        props = {
            "osm_type": "way",
            "osm_id": eid,
            "layer_kind": "tram_way",
            **(el.get("tags") or {}),
        }
        out.append(LineFeature(id=f"way/{eid}", coords=coords, props=props))

    return out


def load_tram_stops_overpass(path: Path) -> list[PointFeature]:
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
            "layer_kind": "tram_stop",
            **tags,
        }
        name = tags.get("name")
        if name:
            props["label"] = name

        out.append(
            PointFeature(
                id=f"{etype}/{eid}",
                lon=float(lon),
                lat=float(lat),
                props=props,
            )
        )

    return out

