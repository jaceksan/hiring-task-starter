from __future__ import annotations

import os


def duckdb_threads() -> int:
    raw = (os.getenv("PANGE_DUCKDB_THREADS") or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except Exception:
            pass
    return max(1, int(os.cpu_count() or 1))


def bounded_cache_put(cache: dict, key, value, *, max_items: int) -> None:
    cache[key] = value
    if len(cache) > max_items:
        try:
            oldest = next(iter(cache.keys()))
            if oldest != key:
                cache.pop(oldest, None)
        except Exception:
            pass
