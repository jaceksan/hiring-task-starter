from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon

from geo.index import transformer_4326_to_3857
from layers.types import Layer, LayerBundle, LineFeature, PointFeature, PolygonFeature


@dataclass(frozen=True)
class ClusterMarker:
    lon: float
    lat: float
    count: int


@dataclass(frozen=True)
class LodBudgets:
    # Primary point layer (typically the one the agent highlights).
    max_points_rendered: int = 2_500
    # Other point layers (kept as actual points; no clustering).
    max_aux_points_rendered: int = 3_000
    max_line_vertices: int = 40_000
    max_poly_vertices: int = 80_000


def apply_lod(
    layers: LayerBundle,
    *,
    view_zoom: float,
    highlight_layer_id: str | None,
    highlight_feature_ids: set[str] | None,
    cluster_points_layer_id: str,
    budgets: LodBudgets | None = None,
) -> tuple[LayerBundle, list[ClusterMarker] | None]:
    """
    Apply zoom-aware level-of-detail policies.

    Important: LOD affects only the *rendered* payload. Spatial reasoning should run on
    the non-LOD features.
    """

    b = budgets or LodBudgets()
    zoom = float(view_zoom)

    poly_layers = [l for l in layers.layers if l.kind == "polygons"]
    line_layers = [l for l in layers.layers if l.kind == "lines"]
    point_layers = [l for l in layers.layers if l.kind == "points"]

    # Polygons: split budget evenly between polygon layers (simple, deterministic).
    poly_budget_each = max(0, int(b.max_poly_vertices // max(1, len(poly_layers))))
    poly_out: dict[str, list[PolygonFeature]] = {}
    for l in poly_layers:
        feats = [f for f in l.features if isinstance(f, PolygonFeature)]
        poly_out[l.id] = _simplify_polygons_until_budget(
            feats, zoom, max_vertices=poly_budget_each
        )

    # Lines: split budget evenly between line layers.
    line_budget_each = max(0, int(b.max_line_vertices // max(1, len(line_layers))))
    line_out: dict[str, list[LineFeature]] = {}
    for l in line_layers:
        feats = [f for f in l.features if isinstance(f, LineFeature)]
        keep_ids = (
            set(highlight_feature_ids or set())
            if highlight_layer_id is not None and l.id == highlight_layer_id
            else None
        )
        line_out[l.id] = _simplify_lines_until_budget(
            feats, zoom, max_vertices=line_budget_each, keep_ids=keep_ids
        )

    # Points: cluster/cap only the configured primary layer; cap others deterministically.
    beer_clusters: list[ClusterMarker] | None = None
    point_out: dict[str, list[PointFeature]] = {}
    for l in point_layers:
        feats = [f for f in l.features if isinstance(f, PointFeature)]
        if l.id == cluster_points_layer_id:
            if _should_cluster_points(zoom, len(feats), b.max_points_rendered):
                beer_clusters = _cluster_points(feats, zoom=zoom)[
                    : b.max_points_rendered
                ]
                point_out[l.id] = (
                    feats  # keep raw for highlight lookup; plot chooses clusters
                )
            elif len(feats) > b.max_points_rendered:
                keep_ids = (
                    set(highlight_feature_ids or set())
                    if highlight_layer_id is not None and l.id == highlight_layer_id
                    else None
                )
                point_out[l.id] = _cap_points(
                    feats, b.max_points_rendered, keep_ids=keep_ids
                )
            else:
                point_out[l.id] = feats
        else:
            point_out[l.id] = (
                _cap_points(feats, b.max_aux_points_rendered, keep_ids=None)
                if len(feats) > b.max_aux_points_rendered
                else feats
            )

    out_layers: list[Layer] = []
    for l in layers.layers:
        if l.kind == "polygons":
            feats = poly_out.get(l.id, [])
            out_layers.append(
                Layer(
                    id=l.id, kind=l.kind, title=l.title, features=feats, style=l.style
                )
            )
        elif l.kind == "lines":
            feats = line_out.get(l.id, [])
            out_layers.append(
                Layer(
                    id=l.id, kind=l.kind, title=l.title, features=feats, style=l.style
                )
            )
        elif l.kind == "points":
            feats = point_out.get(l.id, [])
            out_layers.append(
                Layer(
                    id=l.id, kind=l.kind, title=l.title, features=feats, style=l.style
                )
            )
        else:
            out_layers.append(l)

    return LayerBundle(layers=out_layers), beer_clusters


def _should_cluster_points(zoom: float, n_points: int, max_points: int) -> bool:
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


def _transformer_32633_to_4326() -> Transformer:
    # We cluster in EPSG:3857, so invert that back to 4326.
    return Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)


def _cluster_points(points: list[PointFeature], *, zoom: float) -> list[ClusterMarker]:
    """
    Cluster points using a simple meter-based grid in Web Mercator (EPSG:3857).
    """
    t_fwd = transformer_4326_to_3857()
    t_inv = _transformer_32633_to_4326()
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


def _cap_points(
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


def _count_line_vertices(lines: Iterable[LineFeature]) -> int:
    return sum(len(l.coords) for l in lines)


def _count_poly_vertices(polys: Iterable[PolygonFeature]) -> int:
    return sum(len(r) for p in polys for r in p.rings)


def _simplify_lines_until_budget(
    lines: list[LineFeature],
    zoom: float,
    *,
    max_vertices: int,
    keep_ids: set[str] | None,
) -> list[LineFeature]:
    # Start with a zoom-derived tolerance, then increase until we're under budget.
    base_tol = _line_tol_m(zoom)
    tolerances = [base_tol, base_tol * 2, base_tol * 4, base_tol * 8]

    out = lines
    for tol in tolerances:
        if _count_line_vertices(out) <= max_vertices:
            break
        out = _simplify_lines(lines, tolerance_m=tol)
    if _count_line_vertices(out) > max_vertices:
        out = _cap_lines_to_vertex_budget(out, max_vertices, keep_ids=keep_ids)
    return out


def _simplify_polygons_until_budget(
    polys: list[PolygonFeature],
    zoom: float,
    *,
    max_vertices: int,
) -> list[PolygonFeature]:
    base_tol = _poly_tol_m(zoom)
    tolerances = [base_tol, base_tol * 2, base_tol * 4, base_tol * 8]

    out = polys
    for tol in tolerances:
        if _count_poly_vertices(out) <= max_vertices:
            break
        out = _simplify_polygons(polys, tolerance_m=tol)
    if _count_poly_vertices(out) > max_vertices:
        out = _cap_polys_to_vertex_budget(out, max_vertices)
    return out


def _cap_lines_to_vertex_budget(
    lines: list[LineFeature], max_vertices: int, *, keep_ids: set[str] | None
) -> list[LineFeature]:
    """
    Hard fallback: drop the heaviest features until under budget.
    Deterministic: sort by vertex count desc, then id.
    """
    keep = set(keep_ids or set())
    out = list(lines)
    out.sort(key=lambda l: (-len(l.coords), l.id))
    total = _count_line_vertices(out)
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


def _cap_polys_to_vertex_budget(
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
    total = _count_poly_vertices(out)
    while out and total > max_vertices:
        removed = out.pop(0)
        total -= v(removed)
    out.sort(key=lambda p: p.id)
    return out


def _line_tol_m(zoom: float) -> float:
    if zoom <= 6:
        return 250.0
    if zoom <= 8:
        return 150.0
    if zoom <= 10:
        return 75.0
    if zoom <= 12:
        return 25.0
    return 10.0


def _poly_tol_m(zoom: float) -> float:
    if zoom <= 6:
        return 400.0
    if zoom <= 8:
        return 250.0
    if zoom <= 10:
        return 120.0
    if zoom <= 12:
        return 40.0
    return 15.0


def _simplify_lines(
    lines: list[LineFeature], *, tolerance_m: float
) -> list[LineFeature]:
    t_fwd = transformer_4326_to_3857()
    t_inv = _transformer_32633_to_4326()

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


def _simplify_polygons(
    polys: list[PolygonFeature], *, tolerance_m: float
) -> list[PolygonFeature]:
    t_fwd = transformer_4326_to_3857()
    t_inv = _transformer_32633_to_4326()

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
