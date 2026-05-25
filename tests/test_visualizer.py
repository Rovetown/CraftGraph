"""Tests for the Pyvis HTML visualizer.

Targets edge styling by ``edge_kind``. Ingredient edges keep the default
solid gray; unlocks edges render in a distinct color (still solid);
unlocked_by edges render dashed. Cycle highlighting still overrides
edge_kind styling.
"""

from __future__ import annotations

from pathlib import Path

from craftgraph.graph import build_graph
from craftgraph.models import Ingredient, ModifiedRecipe, ParsedFile
from craftgraph.visualizer import (
    UNLOCKED_BY_EDGE_COLOR,
    UNLOCKS_EDGE_COLOR,
    generate_html,
)


def _pf(recipes: list[ModifiedRecipe]) -> ParsedFile:
    pf = ParsedFile(source_path=Path("t.txt"))
    pf.modified_recipes = recipes
    return pf


def test_unlocks_edge_uses_distinct_color(tmp_path: Path) -> None:
    recipes = [ModifiedRecipe(item_id="Knife", unlocks=["Spear"])]
    graph = build_graph([_pf(recipes)])
    out = tmp_path / "g.html"
    generate_html(graph, out)
    html = out.read_text(encoding="utf-8")
    assert UNLOCKS_EDGE_COLOR in html


def test_unlocked_by_edge_is_dashed(tmp_path: Path) -> None:
    recipes = [ModifiedRecipe(item_id="Sword", unlocked_by=["Knife"])]
    graph = build_graph([_pf(recipes)])
    out = tmp_path / "g.html"
    generate_html(graph, out)
    html = out.read_text(encoding="utf-8")
    assert UNLOCKED_BY_EDGE_COLOR in html
    # vis.js dash attribute is "dashes" in the serialized JSON edge data.
    assert '"dashes": true' in html or '"dashes":true' in html


def test_ingredient_edge_uses_default_color(tmp_path: Path) -> None:
    """Pure ingredient graph keeps the existing normal_edge_color, not unlock colors."""
    recipes = [ModifiedRecipe(item_id="X", ingredients=[Ingredient("Y", 1)])]
    graph = build_graph([_pf(recipes)])
    out = tmp_path / "g.html"
    generate_html(graph, out)
    html = out.read_text(encoding="utf-8")
    # The unlock-specific colors should NOT appear when no unlock edges exist.
    assert UNLOCKS_EDGE_COLOR not in html
    assert UNLOCKED_BY_EDGE_COLOR not in html


def test_cycle_overrides_unlock_styling(tmp_path: Path) -> None:
    """A cycle on an unlocks-edge pair still renders in the cycle color, not unlock color."""
    # A->B via unlocks, B->A via ingredients = cycle.
    recipes = [
        ModifiedRecipe(item_id="A", unlocks=["B"]),
        ModifiedRecipe(item_id="B", ingredients=[Ingredient("A", 1)]),
    ]
    graph = build_graph([_pf(recipes)])
    out = tmp_path / "g.html"
    generate_html(graph, out, cycles=[["A", "B"]])
    html = out.read_text(encoding="utf-8")
    # Cycle color (the existing red) wins; we just sanity-check both nodes exist
    # and at least one edge in the document uses the cycle color setting.
    from craftgraph.config import get_config

    cycle_color = get_config().visualizer.cycle_edge_color
    assert cycle_color in html
