from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app

pytestmark = pytest.mark.integration

TEST_SCENARIO_ID = "prague_population_infrastructure_test"


def test_prague_geoparquet_fixture_files_exist_and_non_empty():
    repo = Path(__file__).resolve().parents[2]
    base = repo / "data/derived/czech_population_infrastructure_large/prague_bbox"
    assert base.exists(), f"Missing fixture directory: {base}"
    for name in ["places.parquet", "roads.parquet", "flood_zones.parquet"]:
        p = base / name
        assert p.exists(), f"Missing GeoParquet fixture: {p}"
        assert p.stat().st_size > 0, f"Empty GeoParquet fixture: {p}"


def test_plot_endpoint_duckdb_geoparquet_prague_small_returns_layers():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": {
                    "minLon": 14.38,
                    "minLat": 50.04,
                    "maxLon": 14.50,
                    "maxLat": 50.12,
                },
                # Keep this test fast (avoid decoding large line/polygon geometries).
                # The scenario uses `minZoomForGeometry` for roads/water; below that threshold
                # those layers should be present but empty.
                "view": {"center": {"lat": 50.0755, "lon": 14.4378}, "zoom": 10.5},
                "context": {"placeCategories": ["urban"]},
            },
            "engine": "duckdb",
            "scenarioId": TEST_SCENARIO_ID,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    meta = payload.get("layout", {}).get("meta", {})
    assert meta.get("stats", {}).get("engine") == "duckdb"
    assert meta.get("stats", {}).get("scenarioId") == TEST_SCENARIO_ID

    names = {t.get("name") for t in payload.get("data", [])}
    # Scenario titles should appear as trace names.
    assert (
        "Places (points)" in names
        or "Places (points) (clusters)" in names
        or "Places (points) (density)" in names
    )
    assert "Roads (lines)" in names
    assert "Flood zones (polygons)" in names
