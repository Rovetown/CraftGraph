"""Tests for the painted-field grid layout helper."""

from __future__ import annotations

import pytest

from craftgraph.painted_fields import FieldRect, FieldState, compute_field_grid
from craftgraph.pin_registry import FieldPin, PinType


@pytest.fixture
def sample_registry() -> list[FieldPin]:
    return [
        FieldPin("item_id", PinType.STRING, label="ItemID", required=True),
        FieldPin("amount", PinType.INT, label="Amount", default=1),
        FieldPin("ingredients", PinType.INGREDIENT_LIST, label="Ingredients"),
        FieldPin("linked", PinType.CSV, label="Linked"),
    ]


class TestFieldGrid:
    def test_excludes_ingredient_list(self, sample_registry):
        rects = compute_field_grid(
            sample_registry,
            node_width=180.0,
            row_height=22.0,
            label_fraction=0.4,
        )
        names = [r.name for r in rects]
        assert "ingredients" not in names
        assert names == ["item_id", "amount", "linked"]

    def test_one_row_per_painted_field(self, sample_registry):
        rects = compute_field_grid(sample_registry, 180.0, 22.0, 0.4)
        # 4 fields - 1 INGREDIENT_LIST excluded == 3 rows.
        assert len(rects) == 3

    def test_label_and_value_split(self, sample_registry):
        rects = compute_field_grid(sample_registry, 200.0, 22.0, 0.4)
        rect = rects[0]
        assert rect.label_rect.width() == pytest.approx(80.0)  # 200 * 0.4
        assert rect.value_rect.width() == pytest.approx(120.0)
        assert rect.label_rect.right() == pytest.approx(rect.value_rect.left())

    def test_row_y_progression(self, sample_registry):
        rects = compute_field_grid(sample_registry, 180.0, 22.0, 0.4)
        assert rects[0].label_rect.top() == 0.0
        assert rects[1].label_rect.top() == pytest.approx(22.0)
        assert rects[2].label_rect.top() == pytest.approx(44.0)

    def test_rects_carry_pin_type(self, sample_registry):
        rects = compute_field_grid(sample_registry, 180.0, 22.0, 0.4)
        types = [r.pin_type for r in rects]
        assert types == [PinType.STRING, PinType.INT, PinType.CSV]

    def test_default_field_state_is_normal(self):
        rect = FieldRect(name="x", pin_type=PinType.STRING,
                         label_rect=None, value_rect=None)
        assert rect.state is FieldState.NORMAL

    def test_total_height(self, sample_registry):
        rects = compute_field_grid(sample_registry, 180.0, 22.0, 0.4)
        assert max(r.label_rect.bottom() for r in rects) == pytest.approx(66.0)


import sys


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
        node = self._make_added_recipe_node(graph)
        self._force_paint(node)
        port_y_by_field = {}
        for port_item, _text in node.view._input_items.items():
            name = port_item.name
            if name.startswith("field_"):
                port_y_by_field[name[len("field_"):]] = port_item.y()
        rects_by_name = {r.name: r for r in node.view._cg_field_rects}
        for field_name, port_y in port_y_by_field.items():
            rect = rects_by_name.get(field_name)
            assert rect is not None, f"missing rect for {field_name}"
            assert rect.value_rect is not None
            assert abs(rect.value_rect.y() - port_y) < 0.5

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
