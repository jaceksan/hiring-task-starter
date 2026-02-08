from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import duckdb

from pathlib import Path

from telemetry.config import telemetry_enabled, telemetry_path
from telemetry.sql import (
    CREATE_EVENTS_TABLE_SQL,
    INSERT_EVENTS_SQL,
    SLOWEST_SQL_TEMPLATE,
    SUMMARY_SQL_TEMPLATE,
)


def _safe_float(v) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


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
            self.conn.execute(CREATE_EVENTS_TABLE_SQL)

    def start(self) -> None:
        if self._worker is not None:
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._run, name="telemetry-writer", daemon=True
        )
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
            SUMMARY_SQL_TEMPLATE.format(where_sql=where_sql),
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
                    "avgPayloadKB": _safe_float(avg_bytes) / 1024.0
                    if avg_bytes is not None
                    else None,
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
            SLOWEST_SQL_TEMPLATE.format(where_sql=" AND ".join(where)),
            params,
        )
        out: list[dict[str, Any]] = []
        for (
            ts_ms,
            engine_v,
            endpoint_v,
            total_ms,
            payload_bytes,
            cache_hit,
            view_zoom,
        ) in rows:
            out.append(
                {
                    "tsMs": int(ts_ms),
                    "engine": engine_v,
                    "endpoint": endpoint_v,
                    "totalMs": _safe_float(total_ms),
                    "payloadKB": (int(payload_bytes) / 1024.0)
                    if payload_bytes is not None
                    else None,
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
                    INSERT_EVENTS_SQL,
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


#
# NOTE: singleton accessors live in `telemetry/singleton.py` to keep this file smaller.
