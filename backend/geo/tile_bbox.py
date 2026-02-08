from __future__ import annotations


def tile_bbox_as_tuple(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """
    Inline tile bbox helper to avoid circular imports.
    """
    # Lazily import to keep this module small and independent.
    from geo.tiles import tile_bbox_4326

    tb = tile_bbox_4326(z, x, y)
    return (tb.min_lon, tb.min_lat, tb.max_lon, tb.max_lat)
