from __future__ import annotations

import math

from geo.aoi import BBox


_MAX_MERCATOR_LAT = 85.05112878


def tile_zoom_for_view_zoom(view_zoom: float) -> int:
    """
    Choose a stable slippy-tile zoom for caching.

    We don't need the tile zoom to equal the visual zoom exactly; we want cache stability
    while panning/zooming.
    """
    z = int(round(float(view_zoom)))
    return max(3, min(13, z))


def lonlat_to_tile(zoom: int, lon: float, lat: float) -> tuple[int, int]:
    """
    Convert lon/lat in EPSG:4326 to slippy tile (x, y) at zoom.
    """
    z = int(zoom)
    n = 2**z

    # Clamp to WebMercator-supported latitudes.
    lat = max(-_MAX_MERCATOR_LAT, min(_MAX_MERCATOR_LAT, float(lat)))

    lon = float(lon)
    lat_rad = math.radians(lat)

    x = int(math.floor((lon + 180.0) / 360.0 * n))
    y = int(
        math.floor(
            (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi)
            / 2.0
            * n
        )
    )
    # Clamp indices to valid tile range.
    x = max(0, min(n - 1, x))
    y = max(0, min(n - 1, y))
    return x, y


def tile_bbox_4326(zoom: int, x: int, y: int) -> BBox:
    """
    Slippy tile (z/x/y) bounds as a WGS84 lon/lat bbox.
    """
    z = int(zoom)
    n = 2**z
    x = int(x)
    y = int(y)

    lon_left = x / n * 360.0 - 180.0
    lon_right = (x + 1) / n * 360.0 - 180.0

    def lat_from_tile_y(tile_y: int) -> float:
        # https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames
        t = math.pi * (1.0 - 2.0 * tile_y / n)
        return math.degrees(math.atan(math.sinh(t)))

    lat_top = lat_from_tile_y(y)
    lat_bottom = lat_from_tile_y(y + 1)

    return BBox(
        min_lon=lon_left, min_lat=lat_bottom, max_lon=lon_right, max_lat=lat_top
    ).normalized()


def tiles_for_bbox(zoom: int, aoi: BBox) -> list[tuple[int, int, int]]:
    """
    List of slippy tiles (z, x, y) covering the AOI bbox.
    """
    z = int(zoom)
    b = aoi.normalized()

    x0, y0 = lonlat_to_tile(z, b.min_lon, b.max_lat)  # top-left
    x1, y1 = lonlat_to_tile(z, b.max_lon, b.min_lat)  # bottom-right

    min_x = min(x0, x1)
    max_x = max(x0, x1)
    min_y = min(y0, y1)
    max_y = max(y0, y1)

    out: list[tuple[int, int, int]] = []
    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            out.append((z, x, y))
    return out
