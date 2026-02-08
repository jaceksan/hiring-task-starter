from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def test_plot_endpoint_returns_plot_payload():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": {"minLon": 14.22, "minLat": 49.94, "maxLon": 14.70, "maxLat": 50.18},
                "view": {"center": {"lat": 50.0755, "lon": 14.4378}, "zoom": 12.0},
            }
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"data", "layout"}
    assert "mapbox" in data["layout"]


def test_plot_endpoint_can_return_clusters_at_low_zoom():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": {"minLon": -20, "minLat": 30, "maxLon": 40, "maxLat": 70},
                "view": {"center": {"lat": 50.0755, "lon": 14.4378}, "zoom": 3.0},
            }
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    names = {t.get("name") for t in payload.get("data", [])}
    assert "Beer POIs (clusters)" in names


def test_plot_endpoint_preserves_highlight_when_provided():
    client = TestClient(app)
    resp = client.post(
        "/plot",
        json={
            "map": {
                "bbox": {"minLon": 14.22, "minLat": 49.94, "maxLon": 14.70, "maxLat": 50.18},
                "view": {"center": {"lat": 50.0755, "lon": 14.4378}, "zoom": 12.0},
            },
            "highlight": {"pointIds": ["node/123", "node/456"], "title": "MyHighlight"},
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    # highlight trace should be present even if the IDs don't exist in current AOI (it will be empty).
    # More importantly: meta should carry highlight info for frontend to round-trip.
    meta = payload.get("layout", {}).get("meta", {})
    assert meta.get("highlight", {}).get("title") == "MyHighlight"

