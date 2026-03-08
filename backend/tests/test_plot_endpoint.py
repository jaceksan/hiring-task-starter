from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from main import app

pytestmark = pytest.mark.integration

TEST_SCENARIO_ID = "prague_population_infrastructure_test"
TEST_CENTER = {"lat": 50.0755, "lon": 14.4378}
TEST_BBOX = {
    "minLon": 14.38,
    "minLat": 50.04,
    "maxLon": 14.50,
    "maxLat": 50.12,
}
LOW_ZOOM_BBOX = {"minLon": 13.8, "minLat": 49.8, "maxLon": 14.9, "maxLat": 50.5}


def test_plot_endpoint_returns_plot_payload():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": TEST_BBOX,
                "view": {"center": TEST_CENTER, "zoom": 10.5},
                "context": {"placeCategories": ["urban"], "floodRiskLevel": "high"},
            },
            "engine": "duckdb",
            "scenarioId": TEST_SCENARIO_ID,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"data", "layout"}
    assert "mapbox" in data["layout"]
    meta = data["layout"].get("meta") or {}
    assert "stats" in meta
    assert meta["stats"].get("engine") == "duckdb"
    assert meta["stats"].get("scenarioId") == TEST_SCENARIO_ID


def test_plot_endpoint_can_return_clusters_at_low_zoom():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": LOW_ZOOM_BBOX,
                "view": {"center": TEST_CENTER, "zoom": 3.0},
                "context": {"placeCategories": ["urban"]},
            },
            "engine": "duckdb",
            "scenarioId": TEST_SCENARIO_ID,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    names = {t.get("name") for t in payload.get("data", [])}
    assert any(
        isinstance(n, str) and (n.endswith("(clusters)") or n.endswith("(density)"))
        for n in names
    )


def test_plot_endpoint_drops_empty_highlight_from_meta_when_unrenderable():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": TEST_BBOX,
                "view": {"center": TEST_CENTER, "zoom": 10.5},
                "context": {"placeCategories": ["urban"]},
            },
            "highlight": {
                "layerId": "places",
                "featureIds": ["node/123", "node/456"],
                "title": "MyHighlight",
            },
            "engine": "duckdb",
            "scenarioId": TEST_SCENARIO_ID,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    meta = payload.get("layout", {}).get("meta", {})
    # Empty/unrenderable highlights are intentionally dropped from meta to avoid stale overlay loops.
    assert "highlight" not in meta
    assert "stats" in meta


def test_plot_endpoint_drops_empty_multi_highlights_from_meta_when_unrenderable():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": TEST_BBOX,
                "view": {"center": TEST_CENTER, "zoom": 10.5},
                "context": {"placeCategories": ["urban"]},
            },
            "highlights": [
                {
                    "layerId": "places",
                    "featureIds": ["node/123"],
                    "title": "Flooded places",
                },
                {
                    "layerId": "roads",
                    "featureIds": ["way/456"],
                    "title": "Escape roads",
                },
            ],
            "engine": "duckdb",
            "scenarioId": TEST_SCENARIO_ID,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    meta = payload.get("layout", {}).get("meta", {})
    assert "highlights" not in meta


def test_plot_endpoint_supports_duckdb_engine(tmp_path, monkeypatch):
    # Use a per-test DuckDB file to avoid lock conflicts with any running local backend.
    db_path = tmp_path / "plot_endpoint.duckdb"
    monkeypatch.setenv("PANGE_DUCKDB_PATH", str(db_path))

    # Clear caches so the app picks up the new path in this process.
    import main
    from engine import duckdb as duckdb_mod
    from engine.duckdb_impl.geoparquet import bundle as geop_bundle

    main._engine.cache_clear()
    duckdb_mod._seeded_base.cache_clear()
    geop_bundle._geoparquet_bundle_cached.cache_clear()

    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": TEST_BBOX,
                # Keep this test fast by staying below minZoomForGeometry for lines/polygons.
                # That still exercises the DuckDB+GeoParquet code path for points + bbox filtering.
                "view": {"center": TEST_CENTER, "zoom": 10.5},
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


def test_plot_endpoint_reports_road_highlight_control_status():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": TEST_BBOX,
                "view": {"center": TEST_CENTER, "zoom": 10.5},
                "context": {"placeCategories": ["urban"]},
            },
            "roadHighlightTypes": ["motorway", "trunks", "secondary"],
            "engine": "duckdb",
            "scenarioId": TEST_SCENARIO_ID,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    stats = payload.get("layout", {}).get("meta", {}).get("stats", {})
    road = stats.get("roadHighlightControl") or {}
    assert road.get("selectedTypes") == ["motorway", "trunk", "secondary"]


def test_plot_endpoint_accepts_request_context():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": TEST_BBOX,
                "view": {"center": TEST_CENTER, "zoom": 10.5},
                "context": {"floodRiskLevel": "high"},
            },
            "engine": "duckdb",
            "scenarioId": TEST_SCENARIO_ID,
        },
    )
    assert resp.status_code == 200


def test_plot_endpoint_reports_flood_selection_stats():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": TEST_BBOX,
                "view": {"center": TEST_CENTER, "zoom": 10.5},
                "context": {"floodRiskLevel": "medium", "selectedFloodZoneIds": []},
            },
            "engine": "duckdb",
            "scenarioId": TEST_SCENARIO_ID,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    stats = payload.get("layout", {}).get("meta", {}).get("stats", {})
    flood = stats.get("floodSelection") or {}
    assert flood.get("mode") == "aoi"
    assert flood.get("riskLevel") == "medium"
    assert isinstance(flood.get("activeZoneCount"), int)


def test_plot_endpoint_reports_place_source_filter_stats():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": TEST_BBOX,
                "view": {"center": TEST_CENTER, "zoom": 10.5},
                "context": {"placeCategories": ["capital"]},
            },
            "engine": "duckdb",
            "scenarioId": TEST_SCENARIO_ID,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    stats = payload.get("layout", {}).get("meta", {}).get("stats", {})
    place = stats.get("placeControl") or {}
    assert "capital" in (place.get("activeCategories") or [])
    assert isinstance(place.get("beforeCount"), int)
    assert isinstance(place.get("afterCount"), int)
    assert int(place.get("afterCount") or 0) <= int(place.get("beforeCount") or 0)


def test_plot_endpoint_reports_flooded_count_prompt_stats_from_highlights():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": TEST_BBOX,
                "view": {"center": TEST_CENTER, "zoom": 10.5},
                "context": {"floodRiskLevel": "high"},
            },
            "highlights": [
                {
                    "layerId": "places",
                    "featureIds": ["node/123"],
                    "title": "Flooded places",
                    "mode": "prompt",
                }
            ],
            "engine": "duckdb",
            "scenarioId": TEST_SCENARIO_ID,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    stats = payload.get("layout", {}).get("meta", {}).get("stats", {})
    assert stats.get("promptType") == "flooded_count"
    count_stats = stats.get("countStats") or {}
    assert count_stats.get("promptType") == "flooded_count"
    assert "approximate" in count_stats
