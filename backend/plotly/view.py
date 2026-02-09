from __future__ import annotations


from layers.types import PointFeature


def fit_view_to_points(
    points: list[PointFeature],
    *,
    viewport: dict[str, int] | None,
) -> tuple[dict[str, float], float]:
    min_lon = min(p.lon for p in points)
    max_lon = max(p.lon for p in points)
    min_lat = min(p.lat for p in points)
    max_lat = max(p.lat for p in points)

    pad_lon = max(0.003, (max_lon - min_lon) * 1.00)
    pad_lat = max(0.003, (max_lat - min_lat) * 1.00)
    min_lon -= pad_lon
    max_lon += pad_lon
    min_lat -= pad_lat
    max_lat += pad_lat

    center = {"lon": (min_lon + max_lon) / 2.0, "lat": (min_lat + max_lat) / 2.0}

    # Approximate Mapbox zoom needed to fit bbox into viewport.
    width = int((viewport or {}).get("width") or 900)
    height = int((viewport or {}).get("height") or 600)
    zoom = bbox_to_zoom(min_lon, min_lat, max_lon, max_lat, width=width, height=height)
    return center, zoom


def bbox_to_zoom(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    *,
    width: int,
    height: int,
) -> float:
    # WebMercator bbox -> zoom heuristic.
    import math

    def lat_to_rad(lat: float) -> float:
        s = math.sin(lat * math.pi / 180.0)
        return math.log((1 + s) / (1 - s)) / 2.0

    lat_rad_min = lat_to_rad(min_lat)
    lat_rad_max = lat_to_rad(max_lat)
    lon_delta = max_lon - min_lon
    lat_delta = (lat_rad_max - lat_rad_min) * 180.0 / math.pi

    # avoid division by zero
    lon_delta = max(lon_delta, 1e-6)
    lat_delta = max(lat_delta, 1e-6)

    # 256px tiles
    zoom_x = math.log2((width * 360.0) / (256.0 * lon_delta))
    zoom_y = math.log2((height * 170.0) / (256.0 * lat_delta))
    return float(min(zoom_x, zoom_y))
