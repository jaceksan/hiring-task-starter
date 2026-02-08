from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Highlight:
    """
    Optional emphasis for a subset of features in a single point/line/polygon layer.
    """

    layer_id: str
    feature_ids: set[str]
    title: str | None = None
