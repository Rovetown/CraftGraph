"""Tests for the painted-field rendering on recipe-chain nodes.

Layout-math tests live in ``tests/test_node_layout.py``; this module
covers integration with NodeGraphQt (paint pass, calc_size override,
alignment to port rows).
"""

from __future__ import annotations

import sys

import pytest

from craftgraph.painted_fields import FieldRect, FieldState
from craftgraph.pin_registry import PinType


class TestFieldRectDefaults:
    def test_default_field_state_is_normal(self):
        rect = FieldRect(
            name="x",
            pin_type=PinType.STRING,
            label_rect=None,
            value_rect=None,
        )
        assert rect.state is FieldState.NORMAL


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def graph(qapp):
    """Fresh NodeGraph for each test."""
    from NodeGraphQt import NodeGraph

    from craftgraph.qt_nodes import all_node_classes

    g = NodeGraph()
    g.set_acyclic(False)
    for cls in all_node_classes():
        g.register_node(cls)
    return g


class TestPaintedFieldsAlignToPortRows:
    """The painted value rect for each field must align to its port row's y."""

    def _make_added_recipe_node(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER

        node = graph.create_node(f"{IDENTIFIER}.AddedRecipeNode")
        node._maybe_build_widgets()
        return node

    def _force_paint(self, node):
        from PySide6.QtGui import QPainter, QPixmap
        from PySide6.QtWidgets import QStyleOptionGraphicsItem

        pixmap = QPixmap(400, 600)
        pixmap.fill()
        painter = QPainter(pixmap)
        option = QStyleOptionGraphicsItem()
        node.view.paint(painter, option, None)
        painter.end()

    def test_value_rects_match_port_y_after_paint(self, qapp, graph):
        """Each value rect's vertical center sits on its port row's center."""
        node = self._make_added_recipe_node(graph)
        self._force_paint(node)
        port_rows_by_field = {}
        for port_item, _text in node.view._input_items.items():
            name = port_item.name
            if name.startswith("field_"):
                port_rows_by_field[name[len("field_"):]] = (
                    port_item.y(),
                    port_item.boundingRect().height(),
                )
        rects_by_name = {r.name: r for r in node.view._cg_field_rects}
        for field_name, (port_y, port_h) in port_rows_by_field.items():
            rect = rects_by_name.get(field_name)
            assert rect is not None, f"missing rect for {field_name}"
            assert rect.value_rect is not None
            port_center = port_y + port_h / 2.0
            value_center = rect.value_rect.y() + rect.value_rect.height() / 2.0
            assert abs(value_center - port_center) < 0.5

    def test_value_rect_does_not_overlap_port_label(self, qapp, graph):
        node = self._make_added_recipe_node(graph)
        self._force_paint(node)
        rects_by_name = {r.name: r for r in node.view._cg_field_rects}
        for port_item, text_item in node.view._input_items.items():
            name = port_item.name
            if not name.startswith("field_"):
                continue
            field_name = name[len("field_"):]
            rect = rects_by_name.get(field_name)
            assert rect is not None
            assert rect.value_rect is not None
            label_right = text_item.x() + text_item.boundingRect().width()
            assert rect.value_rect.left() >= label_right


class TestPaintedFieldsCalcSize:
    def test_calc_size_reserves_value_column(self, qapp, graph):
        from craftgraph.qt_nodes import IDENTIFIER

        node = graph.create_node(f"{IDENTIFIER}.AddedRecipeNode")
        node._maybe_build_widgets()
        base_w, _ = type(node.view).__bases__[0].calc_size(node.view)
        actual_w, _ = node.view.calc_size()
        assert actual_w >= base_w + node.view.VALUE_COLUMN_WIDTH


class TestPaintedFieldsSingleClickEdit:
    def _make_added_recipe_node(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER

        node = graph.create_node(f"{IDENTIFIER}.AddedRecipeNode")
        node._maybe_build_widgets()
        return node

    def _force_paint(self, node):
        from PySide6.QtGui import QPainter, QPixmap
        from PySide6.QtWidgets import QStyleOptionGraphicsItem

        pixmap = QPixmap(400, 600)
        pixmap.fill()
        painter = QPainter(pixmap)
        option = QStyleOptionGraphicsItem()
        node.view.paint(painter, option, None)
        painter.end()

    def _make_event(self, pos, button):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtWidgets import QGraphicsSceneMouseEvent

        event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
        event.setPos(QPointF(pos))
        event.setScenePos(QPointF(pos))
        event.setButton(button)
        event.setButtons(button)
        event.setModifiers(Qt.KeyboardModifier.NoModifier)
        return event

    def test_left_click_on_value_rect_fires_edit_signal(self, qapp, graph):
        from PySide6.QtCore import Qt

        node = self._make_added_recipe_node(graph)
        self._force_paint(node)
        rect_by_name = {r.name: r for r in node.view._cg_field_rects}
        item_id_rect = rect_by_name["item_id"]
        assert item_id_rect.value_rect is not None

        fired: list[tuple] = []
        node._ensure_signals().field_edit_requested.connect(
            lambda n, name, r, val: fired.append((name, val))
        )
        event = self._make_event(item_id_rect.value_rect.center(), Qt.MouseButton.LeftButton)
        node.view.mousePressEvent(event)
        assert fired
        assert fired[0][0] == "item_id"

    def test_right_click_falls_through(self, qapp, graph):
        from PySide6.QtCore import Qt

        node = self._make_added_recipe_node(graph)
        self._force_paint(node)
        rect_by_name = {r.name: r for r in node.view._cg_field_rects}
        item_id_rect = rect_by_name["item_id"]
        assert item_id_rect.value_rect is not None

        fired: list[tuple] = []
        node._ensure_signals().field_edit_requested.connect(
            lambda n, name, r, val: fired.append((name, val))
        )
        event = self._make_event(item_id_rect.value_rect.center(), Qt.MouseButton.RightButton)
        node.view.mousePressEvent(event)
        assert not fired
