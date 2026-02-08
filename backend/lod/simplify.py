from __future__ import annotations

from typing import Iterable

from pyproj import Transformer
from shapely.geometry import LineString, Polygon

from geo.index import transformer_4326_to_3857
from layers.types import LineFeature, PolygonFeature


def count_line_vertices(lines: Iterable[LineFeature]) -> int:
    return sum(len(l.coords) for l in lines)


def count_poly_vertices(polys: Iterable[PolygonFeature]) -> int:
    return sum(len(r) for p in polys for r in p.rings)


def simplify_lines_until_budget(
    lines: list[LineFeature],
    zoom: float,
    *,
    max_vertices: int,
    keep_ids: set[str] | None,
) -> list[LineFeature]:
    # Start with a zoom-derived tolerance, then increase until we're under budget.
    base_tol = line_tol_m(zoom)
    tolerances = [base_tol, base_tol * 2, base_tol * 4, base_tol * 8]

    out = lines
    for tol in tolerances:
        if count_line_vertices(out) <= max_vertices:
            break
        out = simplify_lines(lines, tolerance_m=tol)
    if count_line_vertices(out) > max_vertices:
        out = cap_lines_to_vertex_budget(out, max_vertices, keep_ids=keep_ids)
    return out


def simplify_polygons_until_budget(
    polys: list[PolygonFeature],
    zoom: float,
    *,
    max_vertices: int,
) -> list[PolygonFeature]:
    base_tol = poly_tol_m(zoom)
    tolerances = [base_tol, base_tol * 2, base_tol * 4, base_tol * 8]

    out = polys
    for tol in tolerances:
        if count_poly_vertices(out) <= max_vertices:
            break
        out = simplify_polygons(polys, tolerance_m=tol)
    if count_poly_vertices(out) > max_vertices:
        out = cap_polys_to_vertex_budget(out, max_vertices)
    return out


def cap_lines_to_vertex_budget(
    lines: list[LineFeature], max_vertices: int, *, keep_ids: set[str] | None
) -> list[LineFeature]:
    """
    Hard fallback: drop the heaviest features until under budget.
    Deterministic: sort by vertex count desc, then id.
    """
    keep = set(keep_ids or set())
    out = list(lines)
    out.sort(key=lambda l: (-len(l.coords), l.id))
    total = count_line_vertices(out)
    while out and total > max_vertices:
        # Prefer removing non-kept, heaviest first.
        remove_idx = None
        for i, cand in enumerate(out):
            if cand.id not in keep:
                remove_idx = i
                break
        if remove_idx is None:
            # All remaining are kept; last resort: drop heaviest kept as well.
            remove_idx = 0
        removed = out.pop(remove_idx)
        total -= len(removed.coords)
    # Restore deterministic order for downstream rendering/tests.
    out.sort(key=lambda l: l.id)
    return out


def cap_polys_to_vertex_budget(
    polys: list[PolygonFeature], max_vertices: int
) -> list[PolygonFeature]:
    """
    Hard fallback: drop the heaviest features until under budget.
    Deterministic: sort by vertex count desc, then id.
    """
    out = list(polys)

    def v(p: PolygonFeature) -> int:
        return sum(len(r) for r in p.rings)

    out.sort(key=lambda p: (-v(p), p.id))
    total = count_poly_vertices(out)
    while out and total > max_vertices:
        removed = out.pop(0)
        total -= v(removed)
    out.sort(key=lambda p: p.id)
    return out


def line_tol_m(zoom: float) -> float:
    if zoom <= 6:
        return 250.0
    if zoom <= 8:
        return 150.0
    if zoom <= 10:
        return 75.0
    if zoom <= 12:
        return 25.0
    return 10.0


def poly_tol_m(zoom: float) -> float:
    if zoom <= 6:
        return 400.0
    if zoom <= 8:
        return 250.0
    if zoom <= 10:
        return 120.0
    if zoom <= 12:
        return 40.0
    return 15.0


def simplify_lines(
    lines: list[LineFeature], *, tolerance_m: float
) -> list[LineFeature]:
    t_fwd = transformer_4326_to_3857()
    t_inv = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

    out: list[LineFeature] = []
    for f in lines:
        if len(f.coords) < 2:
            continue
        xs: list[float] = []
        ys: list[float] = []
        for lon, lat in f.coords:
            x, y = t_fwd.transform(lon, lat)
            xs.append(x)
            ys.append(y)
        ls = LineString(list(zip(xs, ys)))
        simp = ls.simplify(tolerance_m, preserve_topology=False)
        if simp.is_empty:
            continue
        coords_m = list(simp.coords)
        if len(coords_m) < 2:
            continue
        coords_ll = [t_inv.transform(x, y) for x, y in coords_m]
        out.append(
            LineFeature(
                id=f.id,
                coords=[(float(lon), float(lat)) for lon, lat in coords_ll],
                props=f.props,
            )
        )
    return out


def simplify_polygons(
    polys: list[PolygonFeature], *, tolerance_m: float
) -> list[PolygonFeature]:
    t_fwd = transformer_4326_to_3857()
    t_inv = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

    out: list[PolygonFeature] = []
    for f in polys:
        if not f.rings or not f.rings[0]:
            continue

        outer = f.rings[0]
        if outer[0] != outer[-1]:
            outer = [*outer, outer[0]]

        outer_m = [t_fwd.transform(lon, lat) for lon, lat in outer]
        try:
            poly = Polygon(outer_m)
        except Exception:
            continue
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            continue

        simp = poly.simplify(tolerance_m, preserve_topology=True)
        if simp.is_empty:
            continue

        # Simplify can yield MultiPolygon; emit one feature per polygon.
        geoms = list(simp.geoms) if hasattr(simp, "geoms") else [simp]
        for idx, g in enumerate(geoms):
            if g.is_empty:
                continue
            try:
                ring_m = list(g.exterior.coords)
            except Exception:
                continue
            if len(ring_m) < 4:
                continue
            ring_ll = [t_inv.transform(x, y) for x, y in ring_m]
            out.append(
                PolygonFeature(
                    id=f"{f.id}-{idx}" if idx else f.id,
                    rings=[[(float(lon), float(lat)) for lon, lat in ring_ll]],
                    props=f.props,
                )
            )

    return out
