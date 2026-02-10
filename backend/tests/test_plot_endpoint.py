from __future__ import annotations


from fastapi.testclient import TestClient

from main import app


def test_plot_endpoint_returns_plot_payload():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": {
                    "minLon": 14.22,
                    "minLat": 49.94,
                    "maxLon": 14.70,
                    "maxLat": 50.18,
                },
                "view": {"center": {"lat": 50.0755, "lon": 14.4378}, "zoom": 12.0},
            },
            "engine": "in_memory",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"data", "layout"}
    assert "mapbox" in data["layout"]
    meta = data["layout"].get("meta") or {}
    assert "stats" in meta
    assert meta["stats"].get("engine") == "in_memory"
    assert meta["stats"].get("scenarioId") == "prague_transport"


def test_plot_endpoint_can_return_clusters_at_low_zoom():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": {"minLon": -20, "minLat": 30, "maxLon": 40, "maxLat": 70},
                "view": {"center": {"lat": 50.0755, "lon": 14.4378}, "zoom": 3.0},
            },
            "engine": "in_memory",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    names = {t.get("name") for t in payload.get("data", [])}
    assert any(isinstance(n, str) and n.endswith("(clusters)") for n in names)


def test_plot_endpoint_preserves_highlight_when_provided():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": {
                    "minLon": 14.22,
                    "minLat": 49.94,
                    "maxLon": 14.70,
                    "maxLat": 50.18,
                },
                "view": {"center": {"lat": 50.0755, "lon": 14.4378}, "zoom": 12.0},
            },
            "highlight": {
                "layerId": "beer_pois",
                "featureIds": ["node/123", "node/456"],
                "title": "MyHighlight",
            },
            "engine": "in_memory",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    # highlight trace should be present even if the IDs don't exist in current AOI (it will be empty).
    # More importantly: meta should carry highlight info for frontend to round-trip.
    meta = payload.get("layout", {}).get("meta", {})
    assert meta.get("highlight", {}).get("title") == "MyHighlight"
    assert meta.get("highlight", {}).get("layerId") == "beer_pois"
    assert "stats" in meta


def test_plot_endpoint_preserves_multiple_highlights_when_provided():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": {
                    "minLon": 14.22,
                    "minLat": 49.94,
                    "maxLon": 14.70,
                    "maxLat": 50.18,
                },
                "view": {"center": {"lat": 50.0755, "lon": 14.4378}, "zoom": 12.0},
            },
            "highlights": [
                {
                    "layerId": "beer_pois",
                    "featureIds": ["node/123"],
                    "title": "Flooded pubs",
                },
                {
                    "layerId": "metro_ways",
                    "featureIds": ["way/456"],
                    "title": "Escape roads",
                },
            ],
            "engine": "in_memory",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    meta = payload.get("layout", {}).get("meta", {})
    assert isinstance(meta.get("highlights"), list)
    assert len(meta.get("highlights")) == 2


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
                "bbox": {
                    "minLon": 14.22,
                    "minLat": 49.94,
                    "maxLon": 14.70,
                    "maxLat": 50.18,
                },
                # Keep this test fast by staying below minZoomForGeometry for lines/polygons.
                # That still exercises the DuckDB+GeoParquet code path for points + bbox filtering.
                "view": {"center": {"lat": 50.0755, "lon": 14.4378}, "zoom": 11.0},
            },
            "engine": "duckdb",
            "scenarioId": "prague_population_infrastructure_small",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    meta = payload.get("layout", {}).get("meta", {})
    assert meta.get("stats", {}).get("engine") == "duckdb"
    assert (
        meta.get("stats", {}).get("scenarioId")
        == "prague_population_infrastructure_small"
    )
