from __future__ import annotations

import os

import duckdb

from telemetry.store import get_store, reset_store


def test_telemetry_store_writes_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "telemetry.duckdb"
    monkeypatch.setenv("PANGE_TELEMETRY_PATH", str(db_path))
    monkeypatch.setenv("PANGE_TELEMETRY", "1")

    store = get_store()
    assert store is not None

    store.record(
        endpoint="/plot",
        prompt=None,
        engine="in_memory",
        view_zoom=10.5,
        aoi={"minLon": 14.3, "minLat": 50.0, "maxLon": 14.5, "maxLat": 50.1},
        stats={"payloadBytes": 123, "timingsMs": {"total": 9.9}},
    )
    store.flush(timeout_s=2.0)

    # Use the existing connection; DuckDB disallows opening the same file with different configs.
    n = int(store.conn.execute("select count(*) from events").fetchone()[0])
    assert n == 1

    row = store.conn.execute("select endpoint, engine from events limit 1").fetchone()
    assert row[0] == "/plot"
    assert row[1] == "in_memory"


def test_telemetry_reset_deletes_db(tmp_path, monkeypatch):
    db_path = tmp_path / "telemetry.duckdb"
    monkeypatch.setenv("PANGE_TELEMETRY_PATH", str(db_path))
    monkeypatch.setenv("PANGE_TELEMETRY", "1")

    store = get_store()
    assert store is not None
    store.record(
        endpoint="/invoke",
        prompt="hello",
        engine="duckdb",
        view_zoom=3.0,
        aoi={"minLon": -1, "minLat": -1, "maxLon": 1, "maxLat": 1},
        stats={},
    )
    assert store.path.resolve() == db_path.resolve()

    reset_store()
    assert not db_path.exists()
