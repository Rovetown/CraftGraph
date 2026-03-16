"""Tests for variable nodes (Phase B).

These tests require the ``qt`` optional dependency group (PySide6 + NodeGraphQt).
They are skipped automatically when those packages are not installed.

Run:  uv run --extra qt pytest tests/test_qt_variable_nodes.py -v
"""

from __future__ import annotations

import sys

import pytest

pytest.importorskip(
    "NodeGraphQt",
    reason="NodeGraphQt not installed (install with: uv sync --extra qt)",
)

from NodeGraphQt import NodeGraph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication (one per test run)."""
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


@pytest.fixture
def graph(qapp):
    """Fresh NodeGraph with all node classes registered."""
    from craftgraph.qt_nodes import all_node_classes
    from craftgraph.qt_variable_nodes import all_variable_node_classes

    g = NodeGraph()
    g.set_acyclic(False)
    for cls in all_node_classes():
        g.register_node(cls)
    for cls in all_variable_node_classes():
        g.register_node(cls)
    return g


# ---------------------------------------------------------------------------
# Base class behavior
# ---------------------------------------------------------------------------


class TestVariableNodeBase:

    def test_is_variable_flag(self, graph):
        node = graph.create_node("com.craftgraph.StringVarNode", name="Test")
        assert node.IS_VARIABLE is True

    def test_has_no_sprite_port(self, graph):
        node = graph.create_node("com.craftgraph.StringVarNode", name="Test")
        assert node.get_input("sprite_in") is None

    def test_has_value_out_port(self, graph):
        node = graph.create_node("com.craftgraph.StringVarNode", name="Test")
        port = node.get_output("value_out")
        assert port is not None

    def test_model_ref_is_none(self, graph):
        node = graph.create_node("com.craftgraph.StringVarNode", name="Test")
        assert node.model_ref is None

    def test_has_var_uuid(self, graph):
        node = graph.create_node("com.craftgraph.StringVarNode", name="Test")
        assert hasattr(node, "_var_uuid")
        assert isinstance(node._var_uuid, str)
        assert len(node._var_uuid) == 8

    def test_var_uuid_unique_per_instance(self, graph):
        n1 = graph.create_node("com.craftgraph.StringVarNode", name="A")
        n2 = graph.create_node("com.craftgraph.StringVarNode", name="B")
        assert n1._var_uuid != n2._var_uuid

    def test_node_color_is_purple(self, graph):
        from craftgraph.qt_variable_nodes import NODE_COLOR_VARIABLE
        node = graph.create_node("com.craftgraph.StringVarNode", name="Test")
        r, g_val, b = node.color()[:3]
        assert (r, g_val, b) == NODE_COLOR_VARIABLE

    def test_variable_node_has_no_field_input_ports(self, graph):
        """Variable nodes produce values; they must NOT have field_* input ports."""
        node = graph.create_node("com.craftgraph.StringVarNode", name="Test")
        field_ports = [p for p in node.input_ports() if p.name().startswith("field_")]
        assert field_ports == []


# ---------------------------------------------------------------------------
# Individual variable node types
# ---------------------------------------------------------------------------


class TestStringVarNode:

    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.StringVarNode", name="Test")
        assert node is not None

    def test_has_value_widget(self, graph):
        node = graph.create_node("com.craftgraph.StringVarNode", name="Test")
        widget = node.get_widget("value")
        assert widget is not None

    def test_default_value_empty_string(self, graph):
        node = graph.create_node("com.craftgraph.StringVarNode", name="Test")
        assert node.get_property("value") == ""


class TestIntVarNode:

    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.IntVarNode", name="Test")
        assert node is not None

    def test_has_value_widget(self, graph):
        node = graph.create_node("com.craftgraph.IntVarNode", name="Test")
        widget = node.get_widget("value")
        assert widget is not None


class TestFloatVarNode:

    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.FloatVarNode", name="Test")
        assert node is not None

    def test_has_value_widget(self, graph):
        node = graph.create_node("com.craftgraph.FloatVarNode", name="Test")
        widget = node.get_widget("value")
        assert widget is not None


class TestBoolVarNode:

    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.BoolVarNode", name="Test")
        assert node is not None

    def test_has_value_widget(self, graph):
        node = graph.create_node("com.craftgraph.BoolVarNode", name="Test")
        widget = node.get_widget("value")
        assert widget is not None

    def test_default_value_false(self, graph):
        node = graph.create_node("com.craftgraph.BoolVarNode", name="Test")
        assert node.get_property("value") is False


class TestCSVListVarNode:

    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.CSVListVarNode", name="Test")
        assert node is not None

    def test_has_value_widget(self, graph):
        node = graph.create_node("com.craftgraph.CSVListVarNode", name="Test")
        widget = node.get_widget("value")
        assert widget is not None


class TestEnumVarNode:

    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.EnumVarNode", name="Test")
        assert node is not None

    def test_has_value_widget(self, graph):
        node = graph.create_node("com.craftgraph.EnumVarNode", name="Test")
        widget = node.get_widget("value")
        assert widget is not None


class TestPathVarNode:

    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.PathVarNode", name="Test")
        assert node is not None

    def test_has_value_widget(self, graph):
        node = graph.create_node("com.craftgraph.PathVarNode", name="Test")
        widget = node.get_widget("value")
        assert widget is not None


class TestColorVarNode:

    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.ColorVarNode", name="Test")
        assert node is not None

    def test_has_value_widget(self, graph):
        node = graph.create_node("com.craftgraph.ColorVarNode", name="Test")
        widget = node.get_widget("value")
        assert widget is not None

    def test_default_value(self, graph):
        node = graph.create_node("com.craftgraph.ColorVarNode", name="Test")
        assert node.get_property("value") == "0.0, 0.0, 0.0"


# ---------------------------------------------------------------------------
# Sync integration (variable connections)
# ---------------------------------------------------------------------------


@pytest.fixture
def sync_setup(graph):
    """Set up a graph with UIToModelHandler wired."""
    from pathlib import Path

    from craftgraph.commands import EditHistory
    from craftgraph.models import ModifiedRecipe, ParsedFile
    from craftgraph.sync import SyncGuard, UIToModelHandler

    recipe = ModifiedRecipe(item_id="Titanium", amount_crafted=1)
    pf = ParsedFile(source_path=Path("test.txt"), modified_recipes=[recipe])

    history = EditHistory()
    guard = SyncGuard()

    recipe_node = graph.create_node(
        "com.craftgraph.ModifiedRecipeNode", name="Recipe",
    )
    recipe_node.model_ref = recipe
    recipe_node.set_edit_history(history)
    recipe_node.populate_from_model()

    string_var = graph.create_node(
        "com.craftgraph.StringVarNode", name="Var",
    )
    string_var.set_edit_history(history)

    int_var = graph.create_node(
        "com.craftgraph.IntVarNode", name="IntVar",
    )
    int_var.set_edit_history(history)

    handler = UIToModelHandler(
        graph=graph,
        history=history,
        guard=guard,
        parsed_files=[pf],
        model_to_node={id(recipe): recipe_node},
    )

    return {
        "graph": graph,
        "recipe": recipe,
        "recipe_node": recipe_node,
        "string_var": string_var,
        "int_var": int_var,
        "handler": handler,
        "history": history,
        "guard": guard,
        "pf": pf,
    }


class TestVariableConnection:

    def test_connect_string_var_to_item_id_updates_model(self, sync_setup):
        s = sync_setup
        s["string_var"].set_property("value", "Gold")
        var_out = s["string_var"].get_output("value_out")
        field_in = s["recipe_node"].get_input("field_item_id")
        var_out.connect_to(field_in)
        assert s["recipe"].item_id == "Gold"

    def test_disconnect_restores_stashed_value(self, sync_setup):
        s = sync_setup
        s["string_var"].set_property("value", "Gold")
        var_out = s["string_var"].get_output("value_out")
        field_in = s["recipe_node"].get_input("field_item_id")
        var_out.connect_to(field_in)
        assert s["recipe"].item_id == "Gold"
        var_out.disconnect_from(field_in)
        assert s["recipe"].item_id == "Titanium"

    def test_type_mismatch_rejects_connection(self, sync_setup):
        s = sync_setup
        int_out = s["int_var"].get_output("value_out")
        field_in = s["recipe_node"].get_input("field_item_id")
        int_out.connect_to(field_in)
        assert not field_in.connected_ports()

    def test_variable_value_change_propagates_to_consumer(self, sync_setup):
        s = sync_setup
        s["string_var"].set_property("value", "Gold")
        var_out = s["string_var"].get_output("value_out")
        field_in = s["recipe_node"].get_input("field_item_id")
        var_out.connect_to(field_in)
        assert s["recipe"].item_id == "Gold"
        # Now change the variable value
        s["string_var"].set_property("value", "Silver")
        # Model should update
        assert s["recipe"].item_id == "Silver"

    def test_variable_propagates_to_multiple_consumers(self, sync_setup):
        s = sync_setup
        from craftgraph.models import ModifiedRecipe

        recipe2 = ModifiedRecipe(item_id="Copper", amount_crafted=1)
        recipe_node2 = s["graph"].create_node(
            "com.craftgraph.ModifiedRecipeNode", name="Recipe2",
        )
        recipe_node2.model_ref = recipe2
        recipe_node2.set_edit_history(s["history"])
        recipe_node2.populate_from_model()

        s["string_var"].set_property("value", "Gold")
        var_out = s["string_var"].get_output("value_out")

        field_in1 = s["recipe_node"].get_input("field_item_id")
        field_in2 = recipe_node2.get_input("field_item_id")
        var_out.connect_to(field_in1)
        var_out.connect_to(field_in2)

        # Change variable value
        s["string_var"].set_property("value", "Diamond")
        assert s["recipe"].item_id == "Diamond"
        assert recipe2.item_id == "Diamond"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestVariableNodeRegistry:

    def test_registry_has_8_active_entries(self):
        from craftgraph.qt_variable_nodes import VARIABLE_NODE_REGISTRY
        # IngredientListVar is a stub, so 8 active
        assert len(VARIABLE_NODE_REGISTRY) >= 8

    def test_all_variable_node_classes_returns_list(self):
        from craftgraph.qt_variable_nodes import all_variable_node_classes
        classes = all_variable_node_classes()
        assert isinstance(classes, list)
        assert len(classes) >= 8

    def test_variable_node_kind_enum_has_9_members(self):
        from craftgraph.qt_variable_nodes import VariableNodeKind
        assert len(VariableNodeKind) == 9
