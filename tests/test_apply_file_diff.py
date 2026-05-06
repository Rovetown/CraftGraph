"""Unit tests for sync.apply_file_diff -- per-tab diff apply layer."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("NodeGraphQt")

from PySide6 import QtWidgets

from craftgraph.model_diff import FileDiff
from craftgraph.models import Ingredient, ModifiedRecipe, ParsedFile


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


@pytest.fixture
def graph(qapp):
    from craftgraph.qt_nodes import all_node_classes
    from NodeGraphQt import NodeGraph

    g = NodeGraph()
    g.set_acyclic(False)
    for cls in all_node_classes():
        g.register_node(cls)
    return g


def _make_tab(graph, parsed_file=None, model_to_node=None):
    """Build a minimal FileTab-like stand-in for the apply layer tests.

    The real FileTab requires editor + history + ui_handler etc., none of
    which apply_file_diff touches. A simple namespace with the three fields
    apply_file_diff actually reads is sufficient.
    """
    from types import SimpleNamespace

    return SimpleNamespace(
        graph=graph,
        parsed_file=parsed_file,
        model_to_node=model_to_node if model_to_node is not None else {},
    )


class TestApplyFileDiffScaffold:
    def test_empty_diff_is_noop(self, graph):
        from craftgraph.sync import apply_file_diff

        old_pf = ParsedFile(source_path=Path("smoke.txt"))
        tab = _make_tab(graph, parsed_file=old_pf)

        new_pf = ParsedFile(source_path=Path("smoke.txt"))
        result = apply_file_diff(
            file_tab=tab,
            diff=FileDiff(added=[], removed=[], modified=[]),
            new_parsed_file=new_pf,
        )
        assert result.nodes_created == []
        assert result.nodes_deleted_ids == []
        assert result.nodes_modified == []
        assert tab.parsed_file is new_pf


class TestApplyRemovePass:
    def test_removes_node_for_removed_recipe(self, graph):
        """A removed entry deletes its node from the graph and from model_to_node."""
        from craftgraph.qt_nodes import IDENTIFIER
        from craftgraph.sync import apply_file_diff

        recipe = ModifiedRecipe(item_id="Titanium")
        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        node.model_ref = recipe
        old_pf = ParsedFile(source_path=Path("f.txt"))
        old_pf.modified_recipes.append(recipe)
        tab = _make_tab(graph, parsed_file=old_pf, model_to_node={id(recipe): node})

        new_pf = ParsedFile(source_path=Path("f.txt"))
        diff = FileDiff(added=[], removed=[recipe], modified=[])

        node_id = node.id
        result = apply_file_diff(file_tab=tab, diff=diff, new_parsed_file=new_pf)

        assert id(recipe) not in tab.model_to_node
        assert node_id not in {n.id for n in graph.all_nodes()}
        assert result.nodes_deleted_ids == [node_id]

    def test_removes_multiple_nodes(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER
        from craftgraph.sync import apply_file_diff

        r1 = ModifiedRecipe(item_id="Alpha")
        r2 = ModifiedRecipe(item_id="Beta")
        n1 = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        n2 = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        n1.model_ref = r1
        n2.model_ref = r2

        old_pf = ParsedFile(source_path=Path("f.txt"))
        old_pf.modified_recipes.extend([r1, r2])
        tab = _make_tab(
            graph,
            parsed_file=old_pf,
            model_to_node={id(r1): n1, id(r2): n2},
        )

        new_pf = ParsedFile(source_path=Path("f.txt"))
        diff = FileDiff(added=[], removed=[r1, r2], modified=[])

        result = apply_file_diff(file_tab=tab, diff=diff, new_parsed_file=new_pf)

        assert tab.model_to_node == {}
        assert len(result.nodes_deleted_ids) == 2

    def test_remove_with_missing_model_to_node_entry_is_safe(self, graph):
        """Drift between model and graph: pop returns None, no crash."""
        from craftgraph.sync import apply_file_diff

        ghost = ModifiedRecipe(item_id="Ghost")
        old_pf = ParsedFile(source_path=Path("f.txt"))
        tab = _make_tab(graph, parsed_file=old_pf, model_to_node={})

        new_pf = ParsedFile(source_path=Path("f.txt"))
        diff = FileDiff(added=[], removed=[ghost], modified=[])

        result = apply_file_diff(file_tab=tab, diff=diff, new_parsed_file=new_pf)

        assert result.nodes_deleted_ids == []
