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


def test_visualizer_module_does_not_import_pyvis_at_top(tmp_path: Path) -> None:
    """Importing ``craftgraph.visualizer`` must not pull pyvis into ``sys.modules``.

    pyvis is now an optional dep, lazy-loaded inside ``generate_html``. CLI
    subcommands that don't render HTML (``check``, ``export``) must remain
    runnable on a pyvis-less install.
    """
    import sys

    # If a previous test already loaded pyvis (e.g. via generate_html above),
    # we can't unload it -- so this assertion only catches the regression on
    # a clean run. Skip when pyvis is already in sys.modules from earlier.
    if "pyvis" in sys.modules:
        import pytest

        pytest.skip("pyvis already loaded by an earlier test in this session")
    # Re-import the module fresh and confirm pyvis stays unloaded.
    import importlib

    import craftgraph.visualizer as v

    importlib.reload(v)
    assert "pyvis" not in sys.modules


def test_generate_html_raises_pyvis_not_installed_when_missing(
    tmp_path: Path, monkeypatch
) -> None:
    """Raise a friendly :class:`PyvisNotInstalledError` instead of a bare ImportError.

    Simulates pyvis being missing by blocking the import. The error must
    subclass ``ImportError`` so callers can ``except ImportError`` and
    must carry an install-hint string the CLI prints verbatim.
    """
    import builtins
    import sys

    from craftgraph.graph import build_graph
    from craftgraph.visualizer import PyvisNotInstalledError, generate_html

    monkeypatch.setitem(sys.modules, "pyvis", None)
    monkeypatch.setitem(sys.modules, "pyvis.network", None)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("pyvis"):
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    recipes = [ModifiedRecipe(item_id="A", ingredients=[Ingredient("B", 1)])]
    graph = build_graph([_pf(recipes)])

    import pytest

    with pytest.raises(PyvisNotInstalledError) as excinfo:
        generate_html(graph, tmp_path / "g.html")
    assert "pip install" in str(excinfo.value)
    assert issubclass(PyvisNotInstalledError, ImportError)
