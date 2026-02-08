from __future__ import annotations

import threading
from typing import cast

import duckdb

from telemetry.store import TelemetryStore, telemetry_enabled, telemetry_path

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
