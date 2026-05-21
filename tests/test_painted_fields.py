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


class TestFieldRectIsIngredient:
    def test_defaults_false(self) -> None:
        from PySide6.QtCore import QRectF

        from craftgraph.pin_registry import PinType

        rect = FieldRect(
            name="item_id",
            pin_type=PinType.STRING,
            label_rect=None,
            value_rect=QRectF(0, 0, 10, 10),
        )
        assert rect.is_ingredient is False

    def test_can_be_set_true(self) -> None:
        from PySide6.QtCore import QRectF

        from craftgraph.pin_registry import PinType

        rect = FieldRect(
            name="ingredient_0",
            pin_type=PinType.INT,
            label_rect=None,
            value_rect=QRectF(0, 0, 10, 10),
            is_ingredient=True,
        )
        assert rect.is_ingredient is True


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
        for port_item, text_item in node.view._input_items.items():
            name = port_item.name
            if name.startswith("field_"):
                row_h = max(
                    port_item.boundingRect().height(),
                    text_item.boundingRect().height(),
                )
                port_rows_by_field[name[len("field_"):]] = (port_item.y(), row_h)
        rects_by_name = {r.name: r for r in node.view._cg_field_rects}
        for field_name, (port_y, row_h) in port_rows_by_field.items():
            rect = rects_by_name.get(field_name)
            assert rect is not None, f"missing rect for {field_name}"
            assert rect.value_rect is not None
            row_center = port_y + row_h / 2.0
            value_center = rect.value_rect.y() + rect.value_rect.height() / 2.0
            assert abs(value_center - row_center) < 0.5

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


class TestRenderAsDispatch:
    """render_as routes paint to either text or swatch path."""

    def test_swatch_field_fills_value_rect(self, qapp, graph):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPainter, QPixmap
        from craftgraph.painted_fields import FieldRect, FieldState
        from craftgraph.pin_registry import PinType

        node = TestPaintedFieldsAlignToPortRows._make_added_recipe_node(
            TestPaintedFieldsAlignToPortRows(), graph
        )
        node.view._cg_field_values = {"swatch_field": "0.5, 0.25, 0.75, 1.0"}
        rect = FieldRect(
            name="swatch_field",
            pin_type=PinType.CSV,
            label_rect=None,
            value_rect=QRectF(0, 0, 40, 20),
            state=FieldState.NORMAL,
            render_as="swatch",
        )

        pixmap = QPixmap(100, 100)
        pixmap.fill(QColor("black"))
        painter = QPainter(pixmap)
        try:
            node.view._paint_one_field(painter, rect)
        finally:
            painter.end()

        center = pixmap.toImage().pixelColor(20, 10)
        assert abs(center.redF() - 0.5) < 0.02
        assert abs(center.greenF() - 0.25) < 0.02
        assert abs(center.blueF() - 0.75) < 0.02

    def test_text_field_fills_with_field_color(self, qapp, graph):
        """Text fields paint an opaque FIELD_FILL_RGB background so the
        floating editor overlays them seamlessly."""
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPainter, QPixmap
        from craftgraph.painted_fields import FIELD_FILL_RGB, FieldRect, FieldState
        from craftgraph.pin_registry import PinType

        node = TestPaintedFieldsAlignToPortRows._make_added_recipe_node(
            TestPaintedFieldsAlignToPortRows(), graph
        )
        node.view._cg_field_values = {"text_field": "Titanium"}
        rect = FieldRect(
            name="text_field",
            pin_type=PinType.STRING,
            label_rect=None,
            value_rect=QRectF(0, 0, 40, 20),
            state=FieldState.NORMAL,
        )

        pixmap = QPixmap(100, 100)
        pixmap.fill(QColor("black"))
        painter = QPainter(pixmap)
        try:
            node.view._paint_one_field(painter, rect)
        finally:
            painter.end()

        # Sample a corner clear of the (left-aligned) text glyphs and border.
        corner = pixmap.toImage().pixelColor(2, 2)
        expected = QColor(*FIELD_FILL_RGB)
        assert abs(corner.redF() - expected.redF()) < 0.02
        assert abs(corner.greenF() - expected.greenF()) < 0.02
        assert abs(corner.blueF() - expected.blueF()) < 0.02


class TestPaintedIngredientRows:
    def _wire(self, graph):
        from craftgraph.models import Ingredient, ModifiedRecipe

        consumer = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Consumer")
        consumer.model_ref = ModifiedRecipe(
            item_id="Consumer",
            ingredients=[Ingredient("Titanium", 4)],
        )
        consumer._maybe_build_widgets()
        src = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Src")
        src.get_output("output").connect_to(consumer.get_input("ingredient_0"))
        return consumer

    def _force_paint(self, node):
        from PySide6.QtGui import QPainter, QPixmap
        from PySide6.QtWidgets import QStyleOptionGraphicsItem

        pixmap = QPixmap(400, 600)
        pixmap.fill()
        painter = QPainter(pixmap)
        node.view.paint(painter, QStyleOptionGraphicsItem(), None)
        painter.end()

    def test_connected_ingredient_gets_value_rect(self, qapp, graph):
        consumer = self._wire(graph)
        self._force_paint(consumer)
        rects = {r.name: r for r in consumer.view._cg_field_rects}
        assert "ingredient_0" in rects
        assert rects["ingredient_0"].is_ingredient is True
        assert rects["ingredient_0"].value_rect is not None

    def test_ingredient_value_text_reflects_required(self, qapp, graph):
        consumer = self._wire(graph)
        self._force_paint(consumer)
        assert consumer.view._cg_ingredient_values["ingredient_0"] == "4"

    def test_ingredient_rect_shares_value_column_with_fields(self, qapp, graph):
        consumer = self._wire(graph)
        self._force_paint(consumer)
        rects = {r.name: r for r in consumer.view._cg_field_rects}
        ing_x = rects["ingredient_0"].value_rect.x()
        field_x = rects["item_id"].value_rect.x()
        assert abs(ing_x - field_x) < 0.5

    def test_empty_ingredient_port_has_no_rect(self, qapp, graph):
        consumer = self._wire(graph)
        self._force_paint(consumer)
        rects = {r.name: r for r in consumer.view._cg_field_rects}
        # ingredient_1 is the spawned empty placeholder.
        assert "ingredient_1" not in rects

    def test_value_text_refreshes_on_repaint_after_change(self, qapp, graph):
        """paint() re-reads ingredient values each call, so an edited
        Required quantity shows on the next frame without a layout rebuild."""
        from craftgraph.models import Ingredient

        consumer = self._wire(graph)
        self._force_paint(consumer)
        assert consumer.view._cg_ingredient_values["ingredient_0"] == "4"
        # Swap the frozen Ingredient the way set_ingredient_required would,
        # without touching port topology, then repaint.
        consumer.model_ref.ingredients[0] = Ingredient("Titanium", 9)
        self._force_paint(consumer)
        assert consumer.view._cg_ingredient_values["ingredient_0"] == "9"


class TestPaintedIngredientClick:
    def _wire(self, graph):
        from craftgraph.models import Ingredient, ModifiedRecipe

        consumer = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Consumer")
        consumer.model_ref = ModifiedRecipe(
            item_id="Consumer",
            ingredients=[Ingredient("Titanium", 4)],
        )
        consumer._maybe_build_widgets()
        src = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Src")
        src.get_output("output").connect_to(consumer.get_input("ingredient_0"))
        return consumer

    def _force_paint(self, node):
        from PySide6.QtGui import QPainter, QPixmap
        from PySide6.QtWidgets import QStyleOptionGraphicsItem

        pixmap = QPixmap(400, 600)
        pixmap.fill()
        painter = QPainter(pixmap)
        node.view.paint(painter, QStyleOptionGraphicsItem(), None)
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

    def test_left_click_on_ingredient_rect_fires_edit_signal(self, qapp, graph):
        from PySide6.QtCore import Qt

        consumer = self._wire(graph)
        self._force_paint(consumer)
        rects = {r.name: r for r in consumer.view._cg_field_rects}
        ing_rect = rects["ingredient_0"]
        assert ing_rect.value_rect is not None

        fired: list[tuple] = []
        consumer._ensure_signals().field_edit_requested.connect(
            lambda n, name, r, val: fired.append((name, val))
        )
        event = self._make_event(ing_rect.value_rect.center(), Qt.MouseButton.LeftButton)
        consumer.view.mousePressEvent(event)
        assert fired
        assert fired[0] == ("ingredient_0", "4")
