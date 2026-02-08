from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ScenarioDataSize(str):
    small = "small"
    large = "large"


class ScenarioCenter(BaseModel):
    lat: float
    lon: float


class ScenarioDefaultView(BaseModel):
    center: ScenarioCenter
    zoom: float = Field(ge=0.0, le=24.0)


LayerSourceType = Literal["geojson_polygons", "overpass_points", "overpass_lines", "geoparquet"]
GeometryKind = Literal["points", "lines", "polygons"]


class ScenarioLayerSource(BaseModel):
    type: LayerSourceType
    path: str
    # Optional per-source options (kept under source to keep YAML self-contained).
    geoparquet: dict[str, Any] | None = None


class ScenarioLayer(BaseModel):
    """
    A generic layer definition.

    All solution-specific semantics should be expressed here (titles, styling, routing roles),
    not in code.
    """

    id: str
    title: str
    kind: GeometryKind
    source: ScenarioLayerSource
    # Plot styling hints (free-form, interpreted by plot builder).
    style: dict[str, Any] = Field(default_factory=dict)


class ScenarioProximityRule(BaseModel):
    layerId: str
    maxMeters: float = Field(gt=0.0)
    penalty: float = Field(default=1.0, ge=0.0)


class ScenarioHighlightRule(BaseModel):
    """
    A rule that highlights a subset of features on the map.

    Intended for demo-friendly prompts like:
    - "show flooded places" (highlight points in mask)
    - "highlight motorways" (highlight lines by fclass)
    """

    keywords: list[str]
    layerId: str
    title: str | None = None
    maxFeatures: int = Field(default=500, ge=1, le=50_000)

    # Optional mask logic (primarily for point layers).
    maskLayerId: str | None = None
    maskMode: Literal["IN_MASK", "OUTSIDE_MASK"] = "IN_MASK"

    # Optional props filter: all conditions must match.
    # Example: {"fclass": ["motorway", "trunk"]}
    props: dict[str, list[str]] | None = None


class ScenarioRouting(BaseModel):
    """
    Minimal prompt-router configuration.
    """

    primaryPointsLayerId: str
    maskPolygonsLayerId: str | None = None
    pointLabelSingular: str = "point"
    pointLabelPlural: str = "points"
    maskLabel: str = "masked area"

    # Keyword hints (kept simple on purpose).
    showLayersKeywords: list[str] = Field(default_factory=lambda: ["show layers", "help", "reset", "start over"])
    countKeywords: list[str] = Field(default_factory=lambda: ["how many"])
    maskKeywords: list[str] = Field(default_factory=lambda: ["flood", "flooded", "water"])
    recommendKeywords: list[str] = Field(default_factory=lambda: ["recommend"])

    # Optional: proximity-based ranking using one or more point layers.
    proximity: list[ScenarioProximityRule] = Field(default_factory=list)

    # Optional: explicit highlight prompts.
    highlightRules: list[ScenarioHighlightRule] = Field(default_factory=list)


class ScenarioPlot(BaseModel):
    # Which point layer is highlightable by the agent.
    highlightLayerId: str
    # Optional per-layer trace title overrides (layerId -> title).
    traceTitles: dict[str, str] | None = None


class ScenarioConfig(BaseModel):
    id: str
    title: str
    defaultView: ScenarioDefaultView
    # UI + engine hints
    dataSize: str = Field(default="small")  # "small" | "large"
    enabled: bool = True

    # Optional per-scenario example prompts shown in the UI.
    examplePrompts: list[str] | None = None

    layers: list[ScenarioLayer]
    routing: ScenarioRouting
    plot: ScenarioPlot

