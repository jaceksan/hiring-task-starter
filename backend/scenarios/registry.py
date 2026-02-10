from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import yaml

from scenarios.types import ScenarioConfig


def _repo_root() -> Path:
    # .../hiring-task-starter/backend/scenarios/registry.py -> repo root is 2 levels up
    return Path(__file__).resolve().parents[2]


def _scenarios_root() -> Path:
    return _repo_root() / "scenarios"


@dataclass(frozen=True)
class ScenarioEntry:
    config: ScenarioConfig
    # Absolute path to scenario.yaml on disk (useful for debugging).
    path: Path


def _iter_scenario_yaml_files() -> Iterable[Path]:
    root = _scenarios_root()
    if not root.exists():
        return []
    # Convention: scenarios/*/scenario.yaml
    return root.glob("*/scenario.yaml")


def _load_yaml(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid scenario yaml root: {path}")
    return data


@lru_cache(maxsize=1)
def get_registry() -> dict[str, ScenarioEntry]:
    out: dict[str, ScenarioEntry] = {}
    for p in sorted(_iter_scenario_yaml_files(), key=lambda x: str(x)):
        cfg = ScenarioConfig.model_validate(_load_yaml(p))
        if cfg.enabled and not cfg.layers:
            raise ValueError(f"Enabled scenario is missing `layers`: {p}")
        out[cfg.id] = ScenarioEntry(config=cfg, path=p)
    return out


def default_scenario_id() -> str:
    reg = get_registry()
    if not reg:
        return "prague_transport"
    if "prague_transport" in reg:
        return "prague_transport"
    # Fall back to stable ordering.
    return next(iter(reg.keys()), "prague_transport")


def list_scenarios() -> list[ScenarioConfig]:
    reg = get_registry()
    return [e.config for e in reg.values()]


def get_scenario(scenario_id: str | None) -> ScenarioEntry:
    reg = get_registry()
    if not reg:
        raise RuntimeError("No scenarios discovered under `scenarios/*/scenario.yaml`")
    sid = (scenario_id or "").strip() or default_scenario_id()
    if sid not in reg:
        # MVP behavior: unknown scenario falls back to default.
        sid = default_scenario_id()
    return reg[sid]


def resolve_repo_path(repo_relative: str) -> Path:
    # Allow both "data/..." and "/data/..." inputs (normalize to repo-relative).
    rel = (repo_relative or "").lstrip("/")
    return _repo_root() / rel


def clear_registry_cache() -> None:
    """
    Clear in-memory scenario registry cache.

    Useful during development: scenario YAML changes are otherwise not picked up until
    the backend process restarts.
    """
    try:
        get_registry.cache_clear()
    except Exception:
        pass
