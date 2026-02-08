from __future__ import annotations

import json
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb


def _safe_float(v) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def telemetry_path() -> Path:
    # Store under repo so it’s easy to share/query (and stays local).
    return Path(os.getenv("PANGE_TELEMETRY_PATH") or (_repo_root() / "data" / "telemetry" / "telemetry.duckdb"))


def telemetry_enabled() -> bool:
    v = (os.getenv("PANGE_TELEMETRY") or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


@dataclass
class TelemetryStore:
    path: Path
    conn: duckdb.DuckDBPyConnection
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _q: "queue.Queue[dict[str, Any]]" = field(default_factory=queue.Queue, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _worker: threading.Thread | None = field(default=None, repr=False)

    def ensure_schema(self) -> None:
        with self._lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                  ts_ms BIGINT,
                  endpoint TEXT,
                  prompt TEXT,
                  engine TEXT,
                  view_zoom DOUBLE,
                  aoi_min_lon DOUBLE,
                  aoi_min_lat DOUBLE,
                  aoi_max_lon DOUBLE,
                  aoi_max_lat DOUBLE,
                  stats_json TEXT
                );
                """
            )

    def start(self) -> None:
        if self._worker is not None:
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._run, name="telemetry-writer", daemon=True)
        self._worker.start()

    def stop(self, *, timeout_s: float = 2.0) -> None:
        """
        Stop the writer thread (best-effort) and prevent further flushes.
        """
        try:
            self._stop.set()
        except Exception:
            pass
        w = self._worker
        if w is not None and w.is_alive():
            try:
                w.join(timeout=timeout_s)
            except Exception:
                pass
        self._worker = None

    def record(
        self,
        *,
        endpoint: str,
        prompt: str | None,
        engine: str,
        view_zoom: float,
        aoi: dict[str, float],
        stats: dict[str, Any],
    ) -> None:
        # Best-effort, non-blocking: enqueue and return.
        self.start()
        try:
            self._q.put_nowait(
                {
                    "ts_ms": int(time.time() * 1000),
                    "endpoint": str(endpoint),
                    "prompt": prompt,
                    "engine": str(engine),
                    "view_zoom": float(view_zoom),
                    "aoi_min_lon": float(aoi["minLon"]),
                    "aoi_min_lat": float(aoi["minLat"]),
                    "aoi_max_lon": float(aoi["maxLon"]),
                    "aoi_max_lat": float(aoi["maxLat"]),
                    "stats_json": json.dumps(stats, ensure_ascii=False),
                }
            )
        except Exception:
            # drop telemetry on overload
            pass

    def flush(self, *, timeout_s: float = 2.0) -> None:
        """
        Best-effort: wait until queued events are processed (used by tests).
        """
        if self._worker is None:
            return
        # Wait for the queue to be drained, then wait a tiny bit for the worker to flush.
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self._q.unfinished_tasks == 0:
                break
            time.sleep(0.01)
        # Give the writer thread time to flush on its time-based trigger.
        time.sleep(0.55)

    def query(self, sql: str, params: list[Any] | None = None) -> list[tuple]:
        """
        Run a read query inside the backend process.

        Rationale: DuckDB uses file locks across processes; if the backend is writing telemetry,
        opening the DB from another process (even read-only) can fail. Querying via API avoids that.
        """
        with self._lock:
            if params:
                return self.conn.execute(sql, params).fetchall()
            return self.conn.execute(sql).fetchall()

    def summary(
        self,
        *,
        engine: str | None = None,
        endpoint: str | None = None,
        since_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        where = []
        params: list[Any] = []
        if engine:
            where.append("engine = ?")
            params.append(engine)
        if endpoint:
            where.append("endpoint = ?")
            params.append(endpoint)
        if since_ms is not None:
            where.append("ts_ms >= ?")
            params.append(int(since_ms))

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        rows = self.query(
            f"""
            SELECT
              engine,
              endpoint,
              COUNT(*) AS n,
              AVG(try_cast(json_extract(stats_json, '$.timingsMs.total') AS DOUBLE)) AS avg_total_ms,
              quantile_cont(try_cast(json_extract(stats_json, '$.timingsMs.total') AS DOUBLE), 0.50) AS p50_total_ms,
              quantile_cont(try_cast(json_extract(stats_json, '$.timingsMs.total') AS DOUBLE), 0.95) AS p95_total_ms,
              quantile_cont(try_cast(json_extract(stats_json, '$.timingsMs.total') AS DOUBLE), 0.99) AS p99_total_ms,
              AVG(try_cast(json_extract(stats_json, '$.payloadBytes') AS DOUBLE)) AS avg_payload_bytes,
              AVG(CASE WHEN try_cast(json_extract(stats_json, '$.cache.cacheHit') AS BOOLEAN) THEN 1 ELSE 0 END) AS cache_hit_rate
            FROM events
            {where_sql}
            GROUP BY engine, endpoint
            ORDER BY engine, endpoint
            """,
            params,
        )

        out: list[dict[str, Any]] = []
        for engine_v, endpoint_v, n, avg_ms, p50, p95, p99, avg_bytes, hit_rate in rows:
            out.append(
                {
                    "engine": engine_v,
                    "endpoint": endpoint_v,
                    "n": int(n),
                    "avgTotalMs": _safe_float(avg_ms),
                    "p50TotalMs": _safe_float(p50),
                    "p95TotalMs": _safe_float(p95),
                    "p99TotalMs": _safe_float(p99),
                    "avgPayloadKB": _safe_float(avg_bytes) / 1024.0 if avg_bytes is not None else None,
                    "cacheHitRate": _safe_float(hit_rate),
                }
            )
        return out

    def slowest(
        self,
        *,
        engine: str | None = None,
        endpoint: str | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        where = ["json_extract(stats_json, '$.timingsMs.total') IS NOT NULL"]
        params: list[Any] = []
        if engine:
            where.append("engine = ?")
            params.append(engine)
        if endpoint:
            where.append("endpoint = ?")
            params.append(endpoint)
        params.append(int(max(1, min(200, limit))))

        rows = self.query(
            f"""
            SELECT
              ts_ms,
              engine,
              endpoint,
              try_cast(json_extract(stats_json, '$.timingsMs.total') AS DOUBLE) AS total_ms,
              try_cast(json_extract(stats_json, '$.payloadBytes') AS BIGINT) AS payload_bytes,
              try_cast(json_extract(stats_json, '$.cache.cacheHit') AS BOOLEAN) AS cache_hit,
              view_zoom
            FROM events
            WHERE {' AND '.join(where)}
            ORDER BY total_ms DESC
            LIMIT ?
            """,
            params,
        )
        out: list[dict[str, Any]] = []
        for ts_ms, engine_v, endpoint_v, total_ms, payload_bytes, cache_hit, view_zoom in rows:
            out.append(
                {
                    "tsMs": int(ts_ms),
                    "engine": engine_v,
                    "endpoint": endpoint_v,
                    "totalMs": _safe_float(total_ms),
                    "payloadKB": (int(payload_bytes) / 1024.0) if payload_bytes is not None else None,
                    "cacheHit": bool(cache_hit) if cache_hit is not None else None,
                    "viewZoom": _safe_float(view_zoom),
                }
            )
        return out

    def reset(self) -> None:
        # Delete the database file to reclaim space.
        # First stop the background thread so it can't write to a closed connection.
        self.stop(timeout_s=2.0)
        with self._lock:
            try:
                self.conn.close()
            except Exception:
                pass
            try:
                self.path.unlink(missing_ok=True)  # py3.12
            except Exception:
                pass

    def _run(self) -> None:
        self.ensure_schema()
        batch: list[dict[str, Any]] = []
        last_flush = time.time()

        def flush_batch() -> None:
            nonlocal batch
            if not batch:
                return
            with self._lock:
                self.conn.executemany(
                    """
                    INSERT INTO events
                      (ts_ms, endpoint, prompt, engine, view_zoom, aoi_min_lon, aoi_min_lat, aoi_max_lon, aoi_max_lat, stats_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            e["ts_ms"],
                            e["endpoint"],
                            e["prompt"],
                            e["engine"],
                            e["view_zoom"],
                            e["aoi_min_lon"],
                            e["aoi_min_lat"],
                            e["aoi_max_lon"],
                            e["aoi_max_lat"],
                            e["stats_json"],
                        )
                        for e in batch
                    ],
                )
                # Make results visible to readers immediately.
                try:
                    self.conn.execute("CHECKPOINT;")
                except Exception:
                    pass
            batch = []

        while not self._stop.is_set():
            try:
                e = self._q.get(timeout=0.1)
            except Exception:
                e = None

            if e is not None:
                batch.append(e)
                self._q.task_done()

            # Flush on size or time.
            now = time.time()
            if len(batch) >= 250 or (batch and (now - last_flush) >= 0.5):
                flush_batch()
                last_flush = now

        # Drain remaining
        try:
            while True:
                e = self._q.get_nowait()
                batch.append(e)
                self._q.task_done()
        except Exception:
            pass
        flush_batch()


_STORE: TelemetryStore | None = None
_STORE_LOCK = threading.RLock()


def get_store() -> TelemetryStore | None:
    global _STORE
    if not telemetry_enabled():
        return None
    with _STORE_LOCK:
        path = telemetry_path()
        if _STORE is not None:
            # If env/config changes the path during a dev session (or across tests),
            # reopen the store on the new path.
            if _STORE.path.resolve() == path.resolve():
                return _STORE
            try:
                _STORE.stop(timeout_s=2.0)
                _STORE.conn.close()
            except Exception:
                pass
            _STORE = None

        path.parent.mkdir(parents=True, exist_ok=True)
        # Allow internal parallelism; we serialize writes in a single writer thread.
        conn = duckdb.connect(str(path))
        _STORE = TelemetryStore(path=path, conn=conn)
        _STORE.ensure_schema()
        _STORE.start()
        return _STORE


def reset_store() -> None:
    global _STORE
    with _STORE_LOCK:
        if _STORE is not None:
            _STORE.reset()
            _STORE = None
        else:
            # Best-effort delete even if not opened yet.
            try:
                p = telemetry_path()
                p.unlink(missing_ok=True)
            except Exception:
                pass

