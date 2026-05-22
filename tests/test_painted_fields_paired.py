"""Tests for FieldState.PAIRED_INCOMPLETE and paired-field validation."""

from __future__ import annotations


import pytest
from PySide6.QtCore import QRectF

from craftgraph.painted_fields import FieldRect, FieldState
from craftgraph.pin_registry import PinType


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


class TestFieldStatePairedIncomplete:
    def test_paired_incomplete_enum_value_exists(self):
        assert FieldState.PAIRED_INCOMPLETE
        assert FieldState.PAIRED_INCOMPLETE.value == "paired_incomplete"


class TestPaintedFieldsPairedBorder:
    def test_paired_incomplete_renders_orange_border(self, qapp):
        """PaintedFieldsNodeItem.paint draws an orange value border for PAIRED_INCOMPLETE."""
        from unittest.mock import MagicMock

        from PySide6.QtGui import QColor

        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        item = PaintedFieldsNodeItem(name="test_node")
        item._cg_field_rects = [
            FieldRect(
                name="pda_group",
                pin_type=PinType.ENUM,
                label_rect=QRectF(0, 0, 50, 22),
                value_rect=QRectF(50, 0, 100, 22),
                state=FieldState.PAIRED_INCOMPLETE,
            )
        ]

        painter = MagicMock()
        item._paint_one_field(painter, item._cg_field_rects[0])

        # Look at the QPen objects passed to painter.setPen
        pens = [call.args[0] for call in painter.setPen.call_args_list]
        colors = [p.color() for p in pens if hasattr(p, "color")]
        # At least one pen must be the orange paired-incomplete color (200, 160, 40)
        orange = QColor(200, 160, 40)
        assert any(
            c.red() == orange.red() and c.green() == orange.green() and c.blue() == orange.blue()
            for c in colors
        ), f"No orange pen used; saw colors {[(c.red(), c.green(), c.blue()) for c in colors]}"


class TestValidatePairedFieldsPaintedPath:
    def _make_added_recipe_node(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER
        node = graph.create_node(f"{IDENTIFIER}.AddedRecipeNode")
        node._maybe_build_widgets()
        return node

    def test_paired_only_one_set_marks_partner(self, qapp, graph):
        node = self._make_added_recipe_node(graph)
        # pda_group set, pda_category empty
        node.set_property("pda_group", "Resources", push_undo=False)
        node.set_property("pda_category", "", push_undo=False)
        node.validate_paired_fields()
        assert node.get_field_state("pda_category") is FieldState.PAIRED_INCOMPLETE
        assert node.get_field_state("pda_group") is FieldState.NORMAL

    def test_paired_both_set_clears_incomplete(self, qapp, graph):
        node = self._make_added_recipe_node(graph)
        node.set_property("pda_group", "Resources", push_undo=False)
        node.set_property("pda_category", "", push_undo=False)
        node.validate_paired_fields()  # marks pda_category
        node.set_property("pda_category", "Metals", push_undo=False)
        node.validate_paired_fields()  # should clear
        assert node.get_field_state("pda_category") is FieldState.NORMAL
        assert node.get_field_state("pda_group") is FieldState.NORMAL

    def test_paired_both_empty_clears_incomplete(self, qapp, graph):
        node = self._make_added_recipe_node(graph)
        # Force a PAIRED_INCOMPLETE state, then clear both fields.
        node.set_property("pda_group", "Resources", push_undo=False)
        node.validate_paired_fields()
        node.set_property("pda_group", "", push_undo=False)
        node.validate_paired_fields()
        assert node.get_field_state("pda_category") is FieldState.NORMAL
        assert node.get_field_state("pda_group") is FieldState.NORMAL

    def test_required_empty_outranks_paired(self, qapp, graph):
        node = self._make_added_recipe_node(graph)
        # Pre-set pda_category to REQUIRED_EMPTY by hand to model the precedence rule.
        node._cg_field_states["pda_category"] = FieldState.REQUIRED_EMPTY
        node.set_property("pda_group", "Resources", push_undo=False)
        node.validate_paired_fields()
        # Stays REQUIRED_EMPTY -- paired logic must not downgrade it.
        assert node.get_field_state("pda_category") is FieldState.REQUIRED_EMPTY


class TestFieldStateAccessor:
    def _make_added_recipe_node(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER

        node = graph.create_node(f"{IDENTIFIER}.AddedRecipeNode")
        node._maybe_build_widgets()
        return node

    def test_get_field_state_after_required_validation(self, qapp, graph):
        node = self._make_added_recipe_node(graph)
        node.validate_required_fields()
        # ItemID is required; default is "" -> REQUIRED_EMPTY.
        assert node.get_field_state("item_id") is FieldState.REQUIRED_EMPTY

    def test_get_field_state_normal_after_filling_required(self, qapp, graph):
        node = self._make_added_recipe_node(graph)
        node.set_property("item_id", "Titanium", push_undo=False)
        node.validate_required_fields()
        assert node.get_field_state("item_id") is FieldState.NORMAL
