from __future__ import annotations

import os
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def telemetry_path() -> Path:
    # Store under repo so it’s easy to share/query (and stays local).
    return Path(
        os.getenv("PANGE_TELEMETRY_PATH")
        or (_repo_root() / "data" / "telemetry" / "telemetry.duckdb")
    )


def telemetry_enabled() -> bool:
    v = (os.getenv("PANGE_TELEMETRY") or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}
