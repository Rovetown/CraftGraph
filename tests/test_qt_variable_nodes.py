"""Tests for variable nodes (Phase B).

These tests require the ``qt`` optional dependency group (PySide6 + NodeGraphQt).
They are skipped automatically when those packages are not installed.

Run:  uv run --extra qt pytest tests/test_qt_variable_nodes.py -v
"""

from __future__ import annotations


import pytest

pytest.importorskip(
    "NodeGraphQt",
    reason="NodeGraphQt not installed (install with: uv sync --extra qt)",
)

from NodeGraphQt import NodeGraph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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

    def test_view_is_painted_item(self, graph):
        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        node = graph.create_node("com.craftgraph.StringVarNode", name="v")
        assert isinstance(node.view, PaintedFieldsNodeItem)

    def test_default_value_empty_string(self, graph):
        node = graph.create_node("com.craftgraph.StringVarNode", name="Test")
        assert node.get_property("value") == ""


class TestIntVarNode:
    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.IntVarNode", name="Test")
        assert node is not None

    def test_view_is_painted_item(self, graph):
        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        node = graph.create_node("com.craftgraph.IntVarNode", name="v")
        assert isinstance(node.view, PaintedFieldsNodeItem)


class TestFloatVarNode:
    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.FloatVarNode", name="Test")
        assert node is not None

    def test_view_is_painted_item(self, graph):
        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        node = graph.create_node("com.craftgraph.FloatVarNode", name="v")
        assert isinstance(node.view, PaintedFieldsNodeItem)


class TestBoolVarNode:
    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.BoolVarNode", name="Test")
        assert node is not None

    def test_view_is_painted_item(self, graph):
        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        node = graph.create_node("com.craftgraph.BoolVarNode", name="v")
        assert isinstance(node.view, PaintedFieldsNodeItem)

    def test_default_value_false(self, graph):
        """Painted model stores bool defaults as strings."""
        node = graph.create_node("com.craftgraph.BoolVarNode", name="Test")
        assert node.get_property("value") == "False"


class TestCSVListVarNode:
    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.CSVListVarNode", name="Test")
        assert node is not None

    def test_view_is_painted_item(self, graph):
        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        node = graph.create_node("com.craftgraph.CSVListVarNode", name="v")
        assert isinstance(node.view, PaintedFieldsNodeItem)


class TestEnumVarNode:
    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.EnumVarNode", name="Test")
        assert node is not None

    def test_view_is_painted_item(self, graph):
        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        node = graph.create_node("com.craftgraph.EnumVarNode", name="v")
        assert isinstance(node.view, PaintedFieldsNodeItem)


class TestPathVarNode:
    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.PathVarNode", name="Test")
        assert node is not None

    def test_view_is_painted_item(self, graph):
        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        node = graph.create_node("com.craftgraph.PathVarNode", name="v")
        assert isinstance(node.view, PaintedFieldsNodeItem)


class TestColorVarNode:
    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.ColorVarNode", name="Test")
        assert node is not None

    def test_view_is_painted_item(self, graph):
        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        node = graph.create_node("com.craftgraph.ColorVarNode", name="v")
        assert isinstance(node.view, PaintedFieldsNodeItem)

    def test_default_value(self, graph):
        node = graph.create_node("com.craftgraph.ColorVarNode", name="Test")
        assert node.get_property("value") == "0.0, 0.0, 0.0"


class TestGetFabricatorNode:
    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.GetFabricatorNode", name="Test")
        assert node is not None

    def test_is_variable(self, graph):
        node = graph.create_node("com.craftgraph.GetFabricatorNode", name="Test")
        assert node.IS_VARIABLE is True

    def test_view_is_painted_item(self, graph):
        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        node = graph.create_node("com.craftgraph.GetFabricatorNode", name="v")
        assert isinstance(node.view, PaintedFieldsNodeItem)

    def test_has_value_out_port(self, graph):
        node = graph.create_node("com.craftgraph.GetFabricatorNode", name="Test")
        port = node.get_output("value_out")
        assert port is not None

    def test_has_no_sprite_port(self, graph):
        node = graph.create_node("com.craftgraph.GetFabricatorNode", name="Test")
        assert node.get_input("sprite_in") is None

    def test_value_is_string_pin_type(self, graph):
        """PinType must be STRING for type-safe connection to path fields."""
        from craftgraph.pin_registry import PinType

        node = graph.create_node("com.craftgraph.GetFabricatorNode", name="Test")
        assert node.FIELD_REGISTRY[0].pin_type == PinType.STRING

    def test_value_pin_is_string_with_combo_options(self, graph):
        """refresh_fab_tab_choices stores choices in _cg_field_options."""
        node = graph.create_node("com.craftgraph.GetFabricatorNode", name="v")
        node.refresh_fab_tab_choices(["FabA", "FabB"])
        assert node._cg_field_options["value"] == ["FabA", "FabB"]

    def test_default_value_empty_when_no_choices(self, graph):
        """Painted default for GetFabricatorNode is an empty string."""
        node = graph.create_node("com.craftgraph.GetFabricatorNode", name="Test")
        assert node.get_property("value") == ""

    def test_refresh_fab_tab_choices(self, graph):
        node = graph.create_node("com.craftgraph.GetFabricatorNode", name="Test")
        node.refresh_fab_tab_choices(["FabA", "FabB"])
        assert node._cg_field_options["value"] == ["FabA", "FabB"]
        node.refresh_fab_tab_choices(["FabC"])
        assert node._cg_field_options["value"] == ["FabC"]


class TestGetTabNode:
    def test_create(self, graph):
        node = graph.create_node("com.craftgraph.GetTabNode", name="Test")
        assert node is not None

    def test_is_variable(self, graph):
        node = graph.create_node("com.craftgraph.GetTabNode", name="Test")
        assert node.IS_VARIABLE is True

    def test_view_is_painted_item(self, graph):
        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        node = graph.create_node("com.craftgraph.GetTabNode", name="v")
        assert isinstance(node.view, PaintedFieldsNodeItem)

    def test_has_value_out_port(self, graph):
        node = graph.create_node("com.craftgraph.GetTabNode", name="Test")
        port = node.get_output("value_out")
        assert port is not None

    def test_value_is_string_pin_type(self, graph):
        from craftgraph.pin_registry import PinType

        node = graph.create_node("com.craftgraph.GetTabNode", name="Test")
        assert node.FIELD_REGISTRY[0].pin_type == PinType.STRING

    def test_value_pin_is_string_with_combo_options(self, graph):
        """refresh_fab_tab_choices stores choices in _cg_field_options."""
        node = graph.create_node("com.craftgraph.GetTabNode", name="v")
        node.refresh_fab_tab_choices(["MyFab/SciTab", "MyFab/AdvTab"])
        assert node._cg_field_options["value"] == ["MyFab/SciTab", "MyFab/AdvTab"]

    def test_refresh_fab_tab_choices(self, graph):
        node = graph.create_node("com.craftgraph.GetTabNode", name="Test")
        node.refresh_fab_tab_choices(["MyFab/SciTab", "MyFab/AdvTab"])
        assert node._cg_field_options["value"] == ["MyFab/SciTab", "MyFab/AdvTab"]
        node.refresh_fab_tab_choices(["MyFab/SciTab"])
        assert node._cg_field_options["value"] == ["MyFab/SciTab"]


# ---------------------------------------------------------------------------
# collect_fab_tab_choices
# ---------------------------------------------------------------------------


class TestCollectFabTabChoices:
    def test_fab_choices_from_parsed_file(self):
        """Fabricator item_ids are collected from parsed files."""
        from pathlib import Path

        from craftgraph.models import CustomFabricator, ParsedFile
        from craftgraph.qt_gui import collect_fab_tab_choices

        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(source_path=Path("fabs.txt"), custom_fabricators=[fab])
        fab_choices, tab_choices = collect_fab_tab_choices([pf])
        assert fab_choices == ["MyFab"]

    def test_tab_choices_resolved_path(self):
        """Tab paths are resolved as fab_id/tab_id."""
        from pathlib import Path

        from craftgraph.models import CraftingTab, CustomFabricator, ParsedFile
        from craftgraph.qt_gui import collect_fab_tab_choices

        tab = CraftingTab(tab_id="SciTab")
        fab = CustomFabricator(item_id="MyFab", tabs=[tab])
        pf = ParsedFile(source_path=Path("fabs.txt"), custom_fabricators=[fab])
        fab_choices, tab_choices = collect_fab_tab_choices([pf])
        assert tab_choices == ["MyFab/SciTab"]

    def test_nested_tab_uses_parent_tab_path(self):
        """Tabs with parent_tab_path use it for full path resolution."""
        from pathlib import Path

        from craftgraph.models import CraftingTab, CustomFabricator, ParsedFile
        from craftgraph.qt_gui import collect_fab_tab_choices

        parent = CraftingTab(tab_id="SciTab")
        child = CraftingTab(tab_id="AdvTab", parent_tab_path="MyFab/SciTab")
        fab = CustomFabricator(item_id="MyFab", tabs=[parent, child])
        pf = ParsedFile(source_path=Path("fabs.txt"), custom_fabricators=[fab])
        _, tab_choices = collect_fab_tab_choices([pf])
        assert "MyFab/SciTab" in tab_choices
        assert "MyFab/SciTab/AdvTab" in tab_choices

    def test_standalone_crafting_tabs_included(self):
        """Standalone crafting_tabs with parent_tab_path are included."""
        from pathlib import Path

        from craftgraph.models import CraftingTab, ParsedFile
        from craftgraph.qt_gui import collect_fab_tab_choices

        tab = CraftingTab(tab_id="ExtraTab", parent_tab_path="SomeFab")
        pf = ParsedFile(source_path=Path("tabs.txt"), crafting_tabs=[tab])
        _, tab_choices = collect_fab_tab_choices([pf])
        assert "SomeFab/ExtraTab" in tab_choices

    def test_standalone_tab_without_parent_excluded(self):
        """Standalone tabs without parent_tab_path are excluded (no fab context)."""
        from pathlib import Path

        from craftgraph.models import CraftingTab, ParsedFile
        from craftgraph.qt_gui import collect_fab_tab_choices

        tab = CraftingTab(tab_id="OrphanTab", parent_tab_path="")
        pf = ParsedFile(source_path=Path("tabs.txt"), crafting_tabs=[tab])
        _, tab_choices = collect_fab_tab_choices([pf])
        assert tab_choices == []

    def test_empty_parsed_files(self):
        """No fabs/tabs returns empty lists."""
        from craftgraph.qt_gui import collect_fab_tab_choices

        fab_choices, tab_choices = collect_fab_tab_choices([])
        assert fab_choices == []
        assert tab_choices == []

    def test_multiple_files(self):
        """Choices aggregated across multiple parsed files."""
        from pathlib import Path

        from craftgraph.models import CraftingTab, CustomFabricator, ParsedFile
        from craftgraph.qt_gui import collect_fab_tab_choices

        fab1 = CustomFabricator(item_id="Fab1", tabs=[CraftingTab(tab_id="T1")])
        fab2 = CustomFabricator(item_id="Fab2", tabs=[CraftingTab(tab_id="T2")])
        pf1 = ParsedFile(source_path=Path("f1.txt"), custom_fabricators=[fab1])
        pf2 = ParsedFile(source_path=Path("f2.txt"), custom_fabricators=[fab2])
        fab_choices, tab_choices = collect_fab_tab_choices([pf1, pf2])
        assert "Fab1" in fab_choices
        assert "Fab2" in fab_choices
        assert "Fab1/T1" in tab_choices
        assert "Fab2/T2" in tab_choices


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
        "com.craftgraph.ModifiedRecipeNode",
        name="Recipe",
    )
    recipe_node.model_ref = recipe
    recipe_node.set_edit_history(history)
    recipe_node.populate_from_model()

    string_var = graph.create_node(
        "com.craftgraph.StringVarNode",
        name="Var",
    )
    string_var.set_edit_history(history)

    int_var = graph.create_node(
        "com.craftgraph.IntVarNode",
        name="IntVar",
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
            "com.craftgraph.ModifiedRecipeNode",
            name="Recipe2",
        )
        recipe_node2.model_ref = recipe2
        recipe_node2.set_edit_history(s["history"])
        # Force eager widget build so field_* ports exist before we connect.
        # populate_from_model is lazy (defers to first paint); _maybe_build_widgets
        # fires the build immediately, making field_item_id available.
        recipe_node2._maybe_build_widgets()
        recipe_node2.populate_from_model()

        s["string_var"].set_property("value", "Gold")
        var_out = s["string_var"].get_output("value_out")

        field_in1 = s["recipe_node"].get_input("field_item_id")
        field_in2 = recipe_node2.get_input("field_item_id")
        var_out.connect_to(field_in1)
        var_out.connect_to(field_in2)

        # Change variable value -- both consumers must update
        s["string_var"].set_property("value", "Diamond")
        assert s["recipe"].item_id == "Diamond"
        assert recipe2.item_id == "Diamond"


# ---------------------------------------------------------------------------
# Get Fab / Get Tab connection integration
# ---------------------------------------------------------------------------


class TestGetFabConnection:
    def test_connect_get_fab_to_path_updates_model(self, sync_setup):
        """Connecting Get Fab to a recipe's path field updates the model."""
        s = sync_setup
        from craftgraph.models import AddedRecipe

        recipe = AddedRecipe(item_id="TestItem", path="")
        added_node = s["graph"].create_node("com.craftgraph.AddedRecipeNode", name="Added")
        added_node.model_ref = recipe
        added_node.set_edit_history(s["history"])
        added_node.populate_from_model()

        get_fab = s["graph"].create_node("com.craftgraph.GetFabricatorNode", name="GetFab")
        get_fab.set_edit_history(s["history"])
        get_fab.refresh_fab_tab_choices(["MyFab", "OtherFab"])
        get_fab.set_property("value", "MyFab")

        var_out = get_fab.get_output("value_out")
        field_in = added_node.get_input("field_path")
        var_out.connect_to(field_in)

        assert recipe.path == "MyFab"

    def test_disconnect_get_fab_restores_stashed_value(self, sync_setup):
        s = sync_setup
        from craftgraph.models import AddedRecipe

        recipe = AddedRecipe(item_id="TestItem", path="OriginalPath")
        added_node = s["graph"].create_node("com.craftgraph.AddedRecipeNode", name="Added")
        added_node.model_ref = recipe
        added_node.set_edit_history(s["history"])
        added_node.populate_from_model()

        get_fab = s["graph"].create_node("com.craftgraph.GetFabricatorNode", name="GetFab")
        get_fab.set_edit_history(s["history"])
        get_fab.refresh_fab_tab_choices(["MyFab", "OtherFab"])
        get_fab.set_property("value", "MyFab")

        var_out = get_fab.get_output("value_out")
        field_in = added_node.get_input("field_path")
        var_out.connect_to(field_in)
        assert recipe.path == "MyFab"

        var_out.disconnect_from(field_in)
        assert recipe.path == "OriginalPath"

    def test_get_tab_value_change_propagates(self, sync_setup):
        """Changing Get Tab dropdown propagates new path to connected recipe."""
        s = sync_setup
        from craftgraph.models import AddedRecipe

        recipe = AddedRecipe(item_id="TestItem", path="")
        added_node = s["graph"].create_node("com.craftgraph.AddedRecipeNode", name="Added")
        added_node.model_ref = recipe
        added_node.set_edit_history(s["history"])
        added_node.populate_from_model()

        get_tab = s["graph"].create_node("com.craftgraph.GetTabNode", name="GetTab")
        get_tab.set_edit_history(s["history"])
        get_tab.refresh_fab_tab_choices(["MyFab/SciTab", "MyFab/AdvTab"])
        get_tab.set_property("value", "MyFab/SciTab")

        var_out = get_tab.get_output("value_out")
        field_in = added_node.get_input("field_path")
        var_out.connect_to(field_in)
        assert recipe.path == "MyFab/SciTab"

        # Change dropdown selection
        get_tab.set_property("value", "MyFab/AdvTab")
        assert recipe.path == "MyFab/AdvTab"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestVariableNodePersistence:
    def test_var_uuid_provides_position_key(self, graph):
        node = graph.create_node("com.craftgraph.StringVarNode", name="Test")
        key = f"VarNode:{node._var_uuid}"
        assert key.startswith("VarNode:")
        assert len(key) == len("VarNode:") + 8


# ---------------------------------------------------------------------------
# GUI registration
# ---------------------------------------------------------------------------


class TestVariableNodeGUIRegistration:
    def test_graph_can_create_all_variable_types(self, graph):
        """All 10 active variable types should be creatable from the graph."""
        type_names = [
            "StringVarNode",
            "IntVarNode",
            "FloatVarNode",
            "BoolVarNode",
            "CSVListVarNode",
            "EnumVarNode",
            "PathVarNode",
            "ColorVarNode",
            "GetFabricatorNode",
            "GetTabNode",
        ]
        for name in type_names:
            node = graph.create_node(f"com.craftgraph.{name}", name=name)
            assert node is not None, f"Failed to create {name}"


# ---------------------------------------------------------------------------
# Promote to Variable
# ---------------------------------------------------------------------------


class TestPromoteToVariable:
    def test_pintype_to_variable_kind_mapping(self):
        from craftgraph.qt_variable_nodes import pintype_to_variable_kind, VariableNodeKind
        from craftgraph.pin_registry import PinType

        assert pintype_to_variable_kind(PinType.STRING) == VariableNodeKind.STRING_VAR
        assert pintype_to_variable_kind(PinType.INT) == VariableNodeKind.INT_VAR
        assert pintype_to_variable_kind(PinType.FLOAT) == VariableNodeKind.FLOAT_VAR
        assert pintype_to_variable_kind(PinType.BOOL) == VariableNodeKind.BOOL_VAR
        assert pintype_to_variable_kind(PinType.CSV) == VariableNodeKind.CSV_LIST_VAR
        assert pintype_to_variable_kind(PinType.ENUM) == VariableNodeKind.ENUM_VAR

    def test_pintype_to_variable_kind_with_override(self):
        from craftgraph.qt_variable_nodes import pintype_to_variable_kind, VariableNodeKind
        from craftgraph.pin_registry import PinType

        assert pintype_to_variable_kind(PinType.STRING, "PathVar") == VariableNodeKind.PATH_VAR
        assert pintype_to_variable_kind(PinType.CSV, "ColorVar") == VariableNodeKind.COLOR_VAR


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestVariableNodeRegistry:
    def test_registry_has_10_active_entries(self):
        from craftgraph.qt_variable_nodes import VARIABLE_NODE_REGISTRY

        # IngredientListVar is a stub, so 10 active
        assert len(VARIABLE_NODE_REGISTRY) >= 10

    def test_all_variable_node_classes_returns_list(self):
        from craftgraph.qt_variable_nodes import all_variable_node_classes

        classes = all_variable_node_classes()
        assert isinstance(classes, list)
        assert len(classes) >= 10

    def test_variable_node_kind_enum_has_11_members(self):
        from craftgraph.qt_variable_nodes import VariableNodeKind

        assert len(VariableNodeKind) == 11
