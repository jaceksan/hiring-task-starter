from engine.duckdb_impl.geoparquet.policy import choose_road_classes_by_budget


def test_choose_road_classes_by_budget_rejects_tertiary_when_over_cap():
    admitted, meta = choose_road_classes_by_budget(
        class_counts={
            "motorway": 120,
            "primary": 240,
            "secondary": 300,
            "tertiary": 800,
        },
        allowed_classes={"motorway", "primary", "secondary", "tertiary"},
        cap=700,
    )
    assert admitted == {"motorway", "primary", "secondary"}
    assert meta.get("rejectedAtClass") == "tertiary"
    assert meta.get("cumulativeAtCutoff") == 660


def test_choose_road_classes_by_budget_keeps_first_group_when_it_exceeds_cap():
    admitted, meta = choose_road_classes_by_budget(
        class_counts={
            "motorway": 1600,
            "primary": 100,
        },
        allowed_classes={"motorway", "primary"},
        cap=1000,
    )
    assert admitted == {"motorway"}
    assert meta.get("oversizedFirstGroup") is True
    assert meta.get("rejectedAtClass") == "motorway"
