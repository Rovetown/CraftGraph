"""ColorVarNode paints a swatch and opens QColorDialog on click."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from craftgraph.qt_variable_nodes import ColorVarNode


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def graph(qapp):
    from NodeGraphQt import NodeGraph
    from craftgraph.qt_nodes import all_node_classes
    from craftgraph.qt_variable_nodes import all_variable_node_classes

    g = NodeGraph()
    for cls in all_node_classes() + all_variable_node_classes():
        g.register_node(cls)
    yield g


class TestColorVarRendering:
    def test_field_render_as_swatch(self):
        fp = ColorVarNode.FIELD_REGISTRY[0]
        assert fp.render_as == "swatch"

    def test_default_value_is_rgb_triple(self, graph):
        node = graph.create_node("com.craftgraph.ColorVarNode", name="c")
        node._maybe_build_widgets()
        assert node._cg_field_values["value"] == "0.0, 0.0, 0.0"


class TestColorVarClick:
    def test_click_opens_color_dialog_and_writes_rgba(self, graph):
        node = graph.create_node("com.craftgraph.ColorVarNode", name="c")
        node._maybe_build_widgets()
        with patch(
            "PySide6.QtWidgets.QColorDialog.getColor",
            return_value=QColor.fromRgbF(0.4, 0.7, 0.2, 1.0),
        ):
            node.open_color_dialog()
        parts = [float(p) for p in node._cg_field_values["value"].split(",")]
        assert abs(parts[0] - 0.4) < 0.01
        assert abs(parts[1] - 0.7) < 0.01
        assert abs(parts[2] - 0.2) < 0.01

    def test_invalid_dialog_result_leaves_value_unchanged(self, graph):
        node = graph.create_node("com.craftgraph.ColorVarNode", name="c")
        node._maybe_build_widgets()
        original = node._cg_field_values["value"]
        with patch(
            "PySide6.QtWidgets.QColorDialog.getColor",
            return_value=QColor(),  # invalid
        ):
            node.open_color_dialog()
        assert node._cg_field_values["value"] == original
