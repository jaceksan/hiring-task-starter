from __future__ import annotations

from layers.types import Layer, LineFeature
from roads.highlight_control import build_road_type_highlights, normalize_road_types


def _line(fid: str, fclass: str, vertices: int) -> LineFeature:
    coords = [(float(i), float(i)) for i in range(max(2, vertices))]
    return LineFeature(id=fid, coords=coords, props={"fclass": fclass})


def test_normalize_road_types_keeps_canonical_order():
    out = normalize_road_types(["trunks", "secondary", "motorway", "secondary"])
    assert out == ["motorway", "trunk", "secondary"]


def test_build_road_highlights_merges_motorway_links():
    roads = Layer(
        id="roads",
        kind="lines",
        title="Roads",
        features=[
            _line("m0", "motorway", 4),
            _line("m1", "motorway_link", 3),
            _line("p1", "primary", 3),
        ],
        style={},
    )
    highlights, status = build_road_type_highlights(
        roads_layer=roads,
        selected_types=["motorway"],
        source_cap_reached=False,
    )
    assert len(highlights) == 1
    assert highlights[0].feature_ids == {"m0", "m1"}
    assert status["visibleTypes"] == ["motorway"]
    assert status["hiddenTypes"] == []


def test_build_road_highlights_hides_when_source_cap_reached():
    roads = Layer(
        id="roads",
        kind="lines",
        title="Roads",
        features=[_line("t1", "trunk", 4), _line("t2", "trunk_link", 4)],
        style={},
    )
    highlights, status = build_road_type_highlights(
        roads_layer=roads,
        selected_types=["trunk"],
        source_cap_reached=True,
    )
    assert highlights == []
    assert status["visibleTypes"] == []
    assert status["hiddenTypes"] == ["trunk"]
    assert status["hiddenReasonByType"]["trunk"] == "sourceCapped"


def test_build_road_highlights_hides_dense_types():
    roads = Layer(
        id="roads",
        kind="lines",
        title="Roads",
        features=[_line(f"p{i}", "primary", 20) for i in range(10)],
        style={},
    )
    highlights, status = build_road_type_highlights(
        roads_layer=roads,
        selected_types=["primary"],
        source_cap_reached=False,
        max_vertices=30,
    )
    assert highlights == []
    assert status["hiddenTypes"] == ["primary"]
    assert status["hiddenReasonByType"]["primary"] == "tooDense"
