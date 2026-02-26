from __future__ import annotations

from pathlib import Path

import duckdb

from engine.duckdb_impl.geoparquet.cluster_counts import (
    enrich_clusters_with_exact_counts,
)
from geo.aoi import BBox
from layers.types import PointFeature
from lod.points import cluster_points, grid_size_m


def _write_points_table(path: Path) -> None:
    rows = [
        # Cluster A (3 total): 2 urban + 1 health
        (14.4000, 50.1000, "urban"),
        (14.4010, 50.1010, "urban"),
        (14.3995, 50.0995, "health"),
        # Cluster B (2 total): 1 urban + 1 shopping
        (14.6000, 50.1000, "urban"),
        (14.6010, 50.1010, "shopping"),
    ]
    conn = duckdb.connect(database=":memory:")
    try:
        conn.execute(
            """
            CREATE TABLE points(
              lon DOUBLE,
              lat DOUBLE,
              place_category VARCHAR,
              xmin DOUBLE,
              ymin DOUBLE,
              xmax DOUBLE,
              ymax DOUBLE
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO points(lon, lat, place_category, xmin, ymin, xmax, ymax)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [(lon, lat, cat, lon, lat, lon, lat) for lon, lat, cat in rows],
        )
        conn.execute("COPY points TO ? (FORMAT PARQUET)", [str(path)])
    finally:
        conn.close()


def test_enrich_clusters_with_exact_counts_returns_full_counts(tmp_path: Path) -> None:
    parquet = tmp_path / "points.parquet"
    _write_points_table(parquet)
    zoom = 8.0
    points = [
        PointFeature(id=f"p{i}", lon=lon, lat=lat, props={"place_category": cat})
        for i, (lon, lat, cat) in enumerate(
            [
                (14.4000, 50.1000, "urban"),
                (14.4010, 50.1010, "urban"),
                (14.3995, 50.0995, "health"),
                (14.6000, 50.1000, "urban"),
                (14.6010, 50.1010, "shopping"),
            ]
        )
    ]
    clusters = cluster_points(points, zoom=zoom)
    aoi = BBox(min_lon=14.2, min_lat=49.9, max_lon=14.8, max_lat=50.3)

    enriched = enrich_clusters_with_exact_counts(
        path=parquet,
        aoi=aoi,
        clusters=clusters,
        grid_m=grid_size_m(zoom),
        place_category_filter=None,
    )

    assert enriched is not None
    assert sorted([c.exact_count for c in enriched]) == [2, 3]


def test_enrich_clusters_with_exact_counts_applies_place_category_filter(
    tmp_path: Path,
) -> None:
    parquet = tmp_path / "points.parquet"
    _write_points_table(parquet)
    zoom = 8.0
    points = [
        PointFeature(id=f"p{i}", lon=lon, lat=lat, props={"place_category": cat})
        for i, (lon, lat, cat) in enumerate(
            [
                (14.4000, 50.1000, "urban"),
                (14.4010, 50.1010, "urban"),
                (14.3995, 50.0995, "health"),
                (14.6000, 50.1000, "urban"),
                (14.6010, 50.1010, "shopping"),
            ]
        )
    ]
    clusters = cluster_points(points, zoom=zoom)
    aoi = BBox(min_lon=14.2, min_lat=49.9, max_lon=14.8, max_lat=50.3)

    enriched = enrich_clusters_with_exact_counts(
        path=parquet,
        aoi=aoi,
        clusters=clusters,
        grid_m=grid_size_m(zoom),
        place_category_filter={"urban"},
    )

    assert enriched is not None
    assert sorted([c.exact_count for c in enriched]) == [1, 2]
