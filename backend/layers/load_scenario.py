from __future__ import annotations

from pathlib import Path

from layers.loaders import (
    load_geojson_polygons,
    load_overpass_lines,
    load_overpass_points,
)
from layers.types import Layer, LayerBundle
from scenarios.registry import get_scenario, resolve_repo_path


def load_scenario_layers(scenario_id: str | None) -> LayerBundle:
    """
    Load scenario-configured layers from files.
    """
    entry = get_scenario(scenario_id)
    cfg = entry.config

    def _p(rel: str) -> Path:
        p = resolve_repo_path(rel)
        if not p.exists():
            raise FileNotFoundError(f"Scenario '{cfg.id}' missing file: {rel}")
        return p

    out: list[Layer] = []
    for layer_cfg in cfg.layers:
        src = layer_cfg.source
        path = _p(src.path)
        if src.type == "geojson_polygons":
            feats = load_geojson_polygons(path)
        elif src.type == "overpass_points":
            feats = load_overpass_points(path)
        elif src.type == "overpass_lines":
            feats = load_overpass_lines(path)
        elif src.type == "geoparquet":
            raise ValueError(
                f"Scenario '{cfg.id}' includes GeoParquet layer '{layer_cfg.id}'. "
                "Use DuckDB engine for GeoParquet-backed scenarios."
            )
        else:
            raise ValueError(f"Unknown layer source type: {src.type}")

        out.append(
            Layer(
                id=layer_cfg.id,
                kind=layer_cfg.kind,
                title=layer_cfg.title,
                features=feats,
                style=layer_cfg.style or {},
            )
        )

    return LayerBundle(layers=out)
