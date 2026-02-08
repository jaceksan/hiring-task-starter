from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def test_get_scenarios_lists_prague_transport():
    client = TestClient(app)
    resp = client.get("/scenarios")
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    ids = {r.get("id") for r in rows}
    assert "prague_transport" in ids
    # Small GeoParquet fixture scenario (Prague bbox).
    assert "prague_population_infrastructure_small" in ids
    # We also expose a large GeoParquet scenario.
    assert "czech_population_infrastructure_large" in ids
