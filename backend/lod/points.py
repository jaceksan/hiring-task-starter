from __future__ import annotations

from dataclasses import dataclass

from pyproj import Transformer

from geo.index import transformer_4326_to_3857
from layers.types import PointFeature


@dataclass(frozen=True)
class ClusterMarker:
    lon: float
    lat: float
    count: int


def should_cluster_points(zoom: float, n_points: int, max_points: int) -> bool:
    # Cluster when zoomed out, or when the raw points would exceed our budget.
    return zoom <= 9.5 or n_points > max_points


def _grid_size_m(zoom: float) -> float:
    # Coarser grids at low zoom.
    if zoom <= 6:
        return 8_000.0
    if zoom <= 8:
        return 4_000.0
    if zoom <= 9:
        return 2_000.0
    if zoom <= 10:
        return 1_000.0
    if zoom <= 11:
        return 500.0
    return 250.0


def _transformer_3857_to_4326() -> Transformer:
    # We cluster in EPSG:3857, so invert that back to 4326.
    return Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)


def cluster_points(points: list[PointFeature], *, zoom: float) -> list[ClusterMarker]:
    """
    Cluster points using a simple meter-based grid in Web Mercator (EPSG:3857).
    """
    t_fwd = transformer_4326_to_3857()
    t_inv = _transformer_3857_to_4326()
    grid = _grid_size_m(zoom)

    buckets: dict[tuple[int, int], tuple[int, float, float]] = {}
    # (cell_x, cell_y) -> (count, sum_x, sum_y)
    for p in points:
        x, y = t_fwd.transform(p.lon, p.lat)
        cx = int(x // grid)
        cy = int(y // grid)
        count, sx, sy = buckets.get((cx, cy), (0, 0.0, 0.0))
        buckets[(cx, cy)] = (count + 1, sx + x, sy + y)

    out: list[ClusterMarker] = []
    for count, sx, sy in buckets.values():
        x = sx / count
        y = sy / count
        lon, lat = t_inv.transform(x, y)
        out.append(ClusterMarker(lon=float(lon), lat=float(lat), count=int(count)))

    # Larger clusters first (nice at low zoom).
    out.sort(key=lambda c: c.count, reverse=True)
    return out


def cap_points(
    points: list[PointFeature], max_points: int, keep_ids: set[str] | None
) -> list[PointFeature]:
    if len(points) <= max_points:
        return points
    keep_ids = keep_ids or set()
    kept = [p for p in points if p.id in keep_ids]
    if len(kept) >= max_points:
        kept.sort(key=lambda p: p.id)
        return kept[:max_points]
    remaining = [p for p in points if p.id not in keep_ids]
    remaining.sort(key=lambda p: p.id)
    return [*kept, *remaining][:max_points]
