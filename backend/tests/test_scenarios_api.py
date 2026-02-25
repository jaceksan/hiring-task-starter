from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def test_get_scenarios_lists_enabled_simplified_scenarios():
    client = TestClient(app)
    resp = client.get("/scenarios")
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    ids = {r.get("id") for r in rows}
    assert "prague_transport" not in ids
    assert "prague_population_infrastructure_small" in ids
    assert "czech_population_infrastructure_large" in ids
    assert len(ids) == 2
    defaults = [r.get("id") for r in rows if r.get("default") is True]
    assert defaults == ["prague_population_infrastructure_small"]
