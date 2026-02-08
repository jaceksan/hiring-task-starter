from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BBox:
    """
    WGS84 bounding box in lon/lat degrees.

    Convention used throughout this repo:
    - minLon, minLat, maxLon, maxLat
    """

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def normalized(self) -> "BBox":
        min_lon = min(self.min_lon, self.max_lon)
        max_lon = max(self.min_lon, self.max_lon)
        min_lat = min(self.min_lat, self.max_lat)
        max_lat = max(self.min_lat, self.max_lat)
        return BBox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)

    def rounded_key(self, decimals: int = 4) -> tuple[float, float, float, float]:
        """
        A stable, hashable key for caching AOI-derived computations.

        decimals=4 is ~11m-ish in latitude, which is good enough for interactive AOI caching.
        """
        b = self.normalized()
        return (
            round(b.min_lon, decimals),
            round(b.min_lat, decimals),
            round(b.max_lon, decimals),
            round(b.max_lat, decimals),
        )
