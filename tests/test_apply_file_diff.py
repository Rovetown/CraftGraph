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
