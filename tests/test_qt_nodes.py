"""Tests for the NodeGraphQt node subclass hierarchy (Step M2).

These tests require the ``qt`` optional dependency group (PySide6 + NodeGraphQt).
They are skipped automatically when those packages are not installed.

Run:  uv run --extra qt pytest tests/test_qt_nodes.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Skip entire module if Qt deps are missing
qt = pytest.importorskip(
    "NodeGraphQt",
    reason="NodeGraphQt not installed (install with: uv sync --extra qt)",
)

from NodeGraphQt import NodeGraph  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def graph(qapp):
    """Fresh NodeGraph for each test."""
    from craftgraph.qt_nodes import all_node_classes

    g = NodeGraph()
    g.set_acyclic(False)
    for cls in all_node_classes():
        g.register_node(cls)
    return g


# ---------------------------------------------------------------------------
# Checkbox 1: Base node class
# ---------------------------------------------------------------------------


class TestCraftGraphBaseNode:
    def test_identifier(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER, ModifiedRecipeNode

        assert ModifiedRecipeNode.__identifier__ == IDENTIFIER

    def test_model_ref_default_none(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Test")
        assert node.model_ref is None

    def test_model_ref_roundtrip(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Test")
        sentinel = {"item_id": "Titanium"}
        node.model_ref = sentinel
        assert node.model_ref is sentinel

    def test_port_deletion_allowed(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Test")
        # port_deletion_allowed is set in __init__
        assert node.port_deletion_allowed()

    def test_has_sprite_port_flag_default_false(self, graph):
        from craftgraph.qt_nodes import CraftGraphBaseNode

        assert CraftGraphBaseNode.HAS_SPRITE_PORT is False

    def test_is_variable_flag_default_false(self, graph):
        from craftgraph.qt_nodes import CraftGraphBaseNode

        assert CraftGraphBaseNode.IS_VARIABLE is False

    def test_sprite_in_port_only_on_alias_and_tab_nodes(self, graph):
        alias = graph.create_node("com.craftgraph.AliasRecipeNode", name="A")
        assert alias.get_input("sprite_in") is not None
        tab = graph.create_node("com.craftgraph.CraftingTabNode", name="T")
        assert tab.get_input("sprite_in") is not None
        mod = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="M")
        assert mod.get_input("sprite_in") is None


class TestFieldInputPorts:
    """Tests for the field_* input ports added by Phase B."""

    def test_modified_recipe_has_field_ports(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Test")
        node._maybe_build_widgets()
        port = node.get_input("field_item_id")
        assert port is not None

    def test_field_port_color_matches_variable_color(self, graph):
        from craftgraph.qt_nodes import PORT_COLOR_VARIABLE

        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Test")
        node._maybe_build_widgets()
        port = node.get_input("field_item_id")
        assert port.color == PORT_COLOR_VARIABLE

    def test_ingredient_list_field_has_no_field_port(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Test")
        port = node.get_input("field_ingredients")
        assert port is None

    def test_added_recipe_has_path_field_port(self, graph):
        node = graph.create_node("com.craftgraph.AddedRecipeNode", name="Test")
        node._maybe_build_widgets()
        port = node.get_input("field_path")
        assert port is not None

    def test_custom_food_has_food_value_field_port(self, graph):
        node = graph.create_node("com.craftgraph.CustomFoodNode", name="Test")
        node._maybe_build_widgets()
        port = node.get_input("field_food_value")
        assert port is not None

    def test_fabricator_has_model_field_port(self, graph):
        node = graph.create_node("com.craftgraph.FabricatorNode", name="Test")
        node._maybe_build_widgets()
        port = node.get_input("field_model")
        assert port is not None


class TestFieldDisableEnable:
    """Tests for disable_field / enable_field stash behavior."""

    def test_disable_field_disables_widget(self, graph):
        from craftgraph.painted_fields import FieldState

        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Test")
        node._maybe_build_widgets()
        node.disable_field("item_id")
        # Painted-fields path: state flips to CONNECTED_TO_VARIABLE, no embedded widget.
        assert node.get_field_state("item_id") is FieldState.CONNECTED_TO_VARIABLE

    def test_enable_field_re_enables_widget(self, graph):
        from craftgraph.painted_fields import FieldState

        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Test")
        node._maybe_build_widgets()
        node.disable_field("item_id")
        node.enable_field("item_id")
        # Painted-fields path: state flips back to NORMAL after enable_field.
        assert node.get_field_state("item_id") is FieldState.NORMAL

    def test_disable_nonexistent_field_is_noop(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Test")
        node.disable_field("nonexistent_field")

    def test_stashed_values_initially_empty(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Test")
        assert node._stashed_values == {}


class TestPreferredVarKind:
    """Tests for preferred_var_kind on FieldPin."""

    def test_field_pin_has_preferred_var_kind(self, graph):
        from craftgraph.pin_registry import FieldPin, PinType

        fp = FieldPin("test", PinType.STRING, preferred_var_kind="PathVar")
        assert fp.preferred_var_kind == "PathVar"

    def test_field_pin_preferred_var_kind_default_none(self, graph):
        from craftgraph.pin_registry import FieldPin, PinType

        fp = FieldPin("test", PinType.STRING)
        assert fp.preferred_var_kind is None


class TestRegistryBuildInfrastructure:
    """Tests for the _build_from_registry / populate_from_model infrastructure."""

    def test_base_class_has_empty_registry(self, graph):
        """CraftGraphBaseNode.FIELD_REGISTRY defaults to empty list."""
        from craftgraph.qt_nodes import CraftGraphBaseNode

        assert CraftGraphBaseNode.FIELD_REGISTRY == []
        assert CraftGraphBaseNode.OUTPUT_PINS == []

    def test_populate_from_model_with_no_model_ref_is_noop(self, graph):
        """populate_from_model() does nothing when model_ref is None."""
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        assert node.model_ref is None
        node.populate_from_model()  # Should not raise

    def test_set_edit_history(self, graph):
        """set_edit_history() stores the history reference."""
        from craftgraph.commands import EditHistory

        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        history = EditHistory()
        node.set_edit_history(history)
        assert node._edit_history is history

    def test_populating_guard_blocks_auto_wiring(self, graph):
        """populate_from_model() should not push commands to EditHistory."""
        from craftgraph.commands import EditHistory
        from craftgraph.models import ModifiedRecipe

        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        recipe = ModifiedRecipe(item_id="Titanium", amount_crafted=3)
        node.model_ref = recipe

        history = EditHistory()
        node.set_edit_history(history)
        node.populate_from_model()

        assert not history.can_undo, "populate_from_model must not push undo commands"


class TestModifiedRecipeRegistry:
    """Tests for ModifiedRecipeNode FIELD_REGISTRY migration."""

    def test_all_registry_fields_have_widgets(self, graph):
        """Every non-INGREDIENT_LIST field should be tracked in the state dict."""
        from craftgraph.pin_registry import PinType

        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        node._maybe_build_widgets()
        field_names = set(node._cg_field_states.keys())
        for fp in node.FIELD_REGISTRY:
            if fp.pin_type == PinType.INGREDIENT_LIST:
                continue
            assert fp.name in field_names, f"Missing painted field: {fp.name}"

    def test_output_pins_exist(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        for op in node.OUTPUT_PINS:
            assert node.get_output(op.name) is not None, f"Missing output: {op.name}"

    def test_registry_has_all_model_fields(self, graph):
        """FIELD_REGISTRY covers all ModifiedRecipe model fields."""
        expected = {
            "item_id",
            "amount_crafted",
            "ingredients",
            "linked_item_ids",
            "unlocks",
            "unlocked_by",
            "force_unlock_at_start",
        }
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        registry_names = {fp.name for fp in node.FIELD_REGISTRY}
        assert expected == registry_names

    def test_populate_from_model_roundtrip(self, graph):
        from craftgraph.models import ModifiedRecipe

        recipe = ModifiedRecipe(
            item_id="Titanium",
            amount_crafted=3,
            linked_item_ids=["Gold", "Silver"],
            force_unlock_at_start=True,
        )
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        node.model_ref = recipe
        node.populate_from_model()
        assert node.get_property("item_id") == "Titanium"
        assert int(node.get_property("amount_crafted")) == 3
        assert node.get_property("linked_item_ids") == "Gold, Silver"
        assert node.get_property("force_unlock_at_start") == "YES"

    def test_new_fields_present(self, graph):
        """Fields that were missing before Phase A should now exist as painted fields."""
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        node._maybe_build_widgets()
        field_names = set(node._cg_field_states.keys())
        assert "linked_item_ids" in field_names
        assert "unlocks" in field_names
        assert "unlocked_by" in field_names
        assert "force_unlock_at_start" in field_names

    def test_dynamic_ingredient_slots_still_work(self, graph):
        """Dynamic ingredient port behavior must survive the migration."""
        recipe = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        src = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Src")
        src.get_output("output").connect_to(recipe.get_input("ingredient_0"))
        assert recipe.get_input("ingredient_1") is not None


class TestAddedRecipeRegistry:
    def test_inherits_parent_fields(self, graph):
        from craftgraph.qt_nodes import ModifiedRecipeNode

        node = graph.create_node("com.craftgraph.AddedRecipeNode", name="A1")
        parent_names = {fp.name for fp in ModifiedRecipeNode.FIELD_REGISTRY}
        node_names = {fp.name for fp in node.FIELD_REGISTRY}
        assert parent_names.issubset(node_names)

    def test_own_fields_present(self, graph):
        node = graph.create_node("com.craftgraph.AddedRecipeNode", name="A1")
        node._maybe_build_widgets()
        # Painted-fields path: properties registered, no embedded widgets.
        assert node.get_property("path") == ""
        assert node.get_property("pda_group") == ""
        assert node.get_property("pda_category") == ""
        assert node.get_widget("path") is None
        assert node.get_widget("pda_group") is None
        assert node.get_widget("pda_category") is None

    def test_populate_path(self, graph):
        from craftgraph.models import AddedRecipe

        recipe = AddedRecipe(item_id="Knife", path="Fabricator/Tools")
        node = graph.create_node("com.craftgraph.AddedRecipeNode", name="A1")
        node.model_ref = recipe
        node.populate_from_model()
        assert node.get_property("path") == "Fabricator/Tools"

    def test_pda_group_nullable(self, graph):
        from craftgraph.models import AddedRecipe

        recipe = AddedRecipe(item_id="Knife", pda_group=None)
        node = graph.create_node("com.craftgraph.AddedRecipeNode", name="A1")
        node.model_ref = recipe
        node.populate_from_model()
        assert node.get_property("pda_group") == ""


class TestAliasRecipeRegistry:
    def test_inherits_added_fields(self, graph):
        node = graph.create_node("com.craftgraph.AliasRecipeNode", name="Al1")
        node._maybe_build_widgets()
        # Painted-fields path: properties registered, no embedded widgets.
        assert node.get_property("path") == ""
        assert node.get_property("pda_group") == ""
        assert node.get_widget("path") is None
        assert node.get_widget("pda_group") is None

    def test_own_fields_present(self, graph):
        node = graph.create_node("com.craftgraph.AliasRecipeNode", name="Al1")
        node._maybe_build_widgets()
        # Painted-fields path: properties registered, no embedded widgets.
        assert node.get_property("display_name") == ""
        assert node.get_property("tooltip") == ""
        assert node.get_property("functional_id") == ""
        assert node.get_property("sprite_item_id") == ""
        assert node.get_widget("display_name") is None
        assert node.get_widget("tooltip") is None
        assert node.get_widget("functional_id") is None
        assert node.get_widget("sprite_item_id") is None

    def test_nullable_string_roundtrip(self, graph):
        from craftgraph.models import AliasRecipe

        recipe = AliasRecipe(item_id="SuperKnife", functional_id=None, sprite_item_id="Knife")
        node = graph.create_node("com.craftgraph.AliasRecipeNode", name="Al1")
        node.model_ref = recipe
        node.populate_from_model()
        assert node.get_property("functional_id") == ""
        assert node.get_property("sprite_item_id") == "Knife"


class TestCustomFoodRegistry:
    def test_inherits_alias_fields(self, graph):
        node = graph.create_node("com.craftgraph.CustomFoodNode", name="F1")
        node._maybe_build_widgets()
        # Painted-fields path: properties registered, no embedded widgets.
        assert node.get_property("display_name") == ""
        assert node.get_property("tooltip") == ""
        assert node.get_widget("display_name") is None
        assert node.get_widget("tooltip") is None

    def test_all_food_stat_fields(self, graph):
        node = graph.create_node("com.craftgraph.CustomFoodNode", name="F1")
        node._maybe_build_widgets()
        # Painted-fields path: properties registered, no embedded widgets.
        for field_name in (
            "food_value",
            "water_value",
            "oxygen_value",
            "health_value",
            "decay_rate_mod",
        ):
            assert node.get_property(field_name) is not None, f"Missing: {field_name}"
            assert node.get_widget(field_name) is None, f"Unexpected widget: {field_name}"

    def test_food_type_and_drink_sound(self, graph):
        node = graph.create_node("com.craftgraph.CustomFoodNode", name="F1")
        node._maybe_build_widgets()
        # Painted-fields path: properties registered, no embedded widgets.
        assert node.get_property("food_type") is not None
        assert node.get_property("use_drink_sound") is not None
        assert node.get_widget("food_type") is None
        assert node.get_widget("use_drink_sound") is None

    def test_populate_food_stats(self, graph):
        from craftgraph.models import CustomFood

        food = CustomFood(
            item_id="SpicyTuna",
            food_value=30,
            water_value=-5,
            oxygen_value=10,
            health_value=5,
            decay_rate_mod=1.5,
        )
        node = graph.create_node("com.craftgraph.CustomFoodNode", name="F1")
        node.model_ref = food
        node.populate_from_model()
        assert int(node.get_property("food_value")) == 30
        assert int(node.get_property("water_value")) == -5
        assert int(node.get_property("oxygen_value")) == 10
        assert float(node.get_property("decay_rate_mod")) == 1.5

    def test_field_count_includes_all_ancestors(self, graph):
        """CustomFoodNode should have all fields from the full inheritance chain."""
        node = graph.create_node("com.craftgraph.CustomFoodNode", name="F1")
        # Modified(7) + Added(3) + Alias(4) + Food(7) = 21
        assert len(node.FIELD_REGISTRY) == 21


# ---------------------------------------------------------------------------
# Checkbox 2: Recipe nodes
# ---------------------------------------------------------------------------


class TestModifiedRecipeNode:
    def test_ports_exist(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        assert node.get_output("output") is not None
        assert node.get_input("hierarchy") is not None
        assert node.get_input("ingredient_0") is not None

    def test_widgets_exist(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        node._maybe_build_widgets()
        # Painted-fields path: fields are tracked in _cg_field_states, not widgets.
        field_names = set(node._cg_field_states.keys())
        assert "item_id" in field_names
        assert "amount_crafted" in field_names

    def test_dynamic_slot_on_connect(self, graph):
        """Connecting to ingredient_0 should spawn ingredient_1."""
        recipe = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        ing = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Src")

        ing_ports = [p for p in recipe.input_ports() if p.name().startswith("ingredient_")]
        initial_count = len(ing_ports)
        assert initial_count == 1

        ing.output(0).connect_to(recipe.get_input("ingredient_0"))

        after_ports = [p for p in recipe.input_ports() if p.name().startswith("ingredient_")]
        after_count = len(after_ports)
        assert after_count == 2
        assert recipe.get_input("ingredient_1") is not None

    def test_dynamic_slot_cleanup_on_disconnect(self, graph):
        """Disconnecting should remove trailing empty ingredient slots."""
        recipe = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        src = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Src")

        # Connect to spawn ingredient_1
        src.output(0).connect_to(recipe.get_input("ingredient_0"))
        assert recipe.get_input("ingredient_1") is not None

        # Disconnect -- should remove the trailing empty slot
        src.output(0).disconnect_from(recipe.get_input("ingredient_0"))

        # Only ingredient_0 should remain
        ing_ports = [p for p in recipe.input_ports() if p.name().startswith("ingredient_")]
        assert len(ing_ports) == 1

    def test_node_color(self, graph):
        from craftgraph.qt_nodes import NODE_COLOR_MODIFIED_RECIPE

        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        assert node.color() == NODE_COLOR_MODIFIED_RECIPE


class TestAddedRecipeNode:
    def test_inherits_recipe_ports(self, graph):
        node = graph.create_node("com.craftgraph.AddedRecipeNode", name="A1")
        assert node.get_output("output") is not None
        assert node.get_input("hierarchy") is not None
        assert node.get_input("ingredient_0") is not None

    def test_path_property_registered(self, graph):
        node = graph.create_node("com.craftgraph.AddedRecipeNode", name="A1")
        node._maybe_build_widgets()
        # Painted-fields path: property registered, no embedded widget.
        assert node.get_property("path") == ""
        assert node.get_widget("path") is None

    def test_node_color(self, graph):
        from craftgraph.qt_nodes import NODE_COLOR_ADDED_RECIPE

        node = graph.create_node("com.craftgraph.AddedRecipeNode", name="A1")
        assert node.color() == NODE_COLOR_ADDED_RECIPE

    def test_dynamic_slots_inherited(self, graph):
        recipe = graph.create_node("com.craftgraph.AddedRecipeNode", name="A1")
        src = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Src")
        src.output(0).connect_to(recipe.get_input("ingredient_0"))
        assert recipe.get_input("ingredient_1") is not None


class TestAliasRecipeNode:
    def test_display_name_and_tooltip_properties_registered(self, graph):
        node = graph.create_node("com.craftgraph.AliasRecipeNode", name="Al1")
        node._maybe_build_widgets()
        # Painted-fields path: properties registered, no embedded widgets.
        assert node.get_property("display_name") == ""
        assert node.get_property("tooltip") == ""
        assert node.get_widget("display_name") is None
        assert node.get_widget("tooltip") is None

    def test_inherits_path_property_registered(self, graph):
        node = graph.create_node("com.craftgraph.AliasRecipeNode", name="Al1")
        node._maybe_build_widgets()
        # Painted-fields path: property registered, no embedded widget.
        assert node.get_property("path") == ""
        assert node.get_widget("path") is None

    def test_node_color(self, graph):
        from craftgraph.qt_nodes import NODE_COLOR_ALIAS_RECIPE

        node = graph.create_node("com.craftgraph.AliasRecipeNode", name="Al1")
        assert node.color() == NODE_COLOR_ALIAS_RECIPE


class TestCustomFoodNode:
    def test_food_stat_properties_registered(self, graph):
        node = graph.create_node("com.craftgraph.CustomFoodNode", name="F1")
        node._maybe_build_widgets()
        # Painted-fields path: properties registered, no embedded widgets.
        assert node.get_property("food_value") is not None
        assert node.get_property("water_value") is not None
        assert node.get_widget("food_value") is None
        assert node.get_widget("water_value") is None

    def test_inherits_alias_properties_registered(self, graph):
        node = graph.create_node("com.craftgraph.CustomFoodNode", name="F1")
        node._maybe_build_widgets()
        # Painted-fields path: properties registered, no embedded widgets.
        assert node.get_property("display_name") == ""
        assert node.get_property("tooltip") == ""
        assert node.get_property("path") == ""
        assert node.get_widget("display_name") is None
        assert node.get_widget("tooltip") is None
        assert node.get_widget("path") is None

    def test_node_color(self, graph):
        from craftgraph.qt_nodes import NODE_COLOR_CUSTOM_FOOD

        node = graph.create_node("com.craftgraph.CustomFoodNode", name="F1")
        assert node.color() == NODE_COLOR_CUSTOM_FOOD


# ---------------------------------------------------------------------------
# Checkbox 3: Container nodes
# ---------------------------------------------------------------------------


class TestFabricatorNode:
    def test_ports(self, graph):
        node = graph.create_node("com.craftgraph.FabricatorNode", name="Fab1")
        node._maybe_build_widgets()
        # SPLIT_OUTPUTS: typed output ports instead of single "children"
        for name in ("tabs_out", "added_out", "alias_out", "foods_out", "moved_out"):
            assert node.get_output(name) is not None, f"Missing output: {name}"
        # Fabricator has 11 field_* ports + ingredient_0 = 12 (no sprite_in)
        assert node.get_input("sprite_in") is None
        assert node.get_input("ingredient_0") is not None
        assert len(node.input_ports()) == 12

    def test_fields_accessible(self, graph):
        node = graph.create_node("com.craftgraph.FabricatorNode", name="Fab1")
        node._maybe_build_widgets()
        assert node.get_property("item_id") is not None
        assert node.get_property("display_name") is not None
        assert node.get_property("model") is not None

    def test_dynamic_ingredient_slot_on_connect(self, graph):
        """Connecting to ingredient_0 should spawn ingredient_1."""
        fab = graph.create_node("com.craftgraph.FabricatorNode", name="Fab1")
        src = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Src")

        ing_ports = [p for p in fab.input_ports() if p.name().startswith("ingredient_")]
        assert len(ing_ports) == 1

        src.output(0).connect_to(fab.get_input("ingredient_0"))

        after_ports = [p for p in fab.input_ports() if p.name().startswith("ingredient_")]
        assert len(after_ports) == 2
        assert fab.get_input("ingredient_1") is not None

    def test_dynamic_ingredient_slot_cleanup_on_disconnect(self, graph):
        """Disconnecting should remove trailing empty ingredient slots."""
        fab = graph.create_node("com.craftgraph.FabricatorNode", name="Fab1")
        src = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Src")

        src.output(0).connect_to(fab.get_input("ingredient_0"))
        assert fab.get_input("ingredient_1") is not None

        src.output(0).disconnect_from(fab.get_input("ingredient_0"))

        ing_ports = [p for p in fab.input_ports() if p.name().startswith("ingredient_")]
        assert len(ing_ports) == 1

    def test_node_color(self, graph):
        from craftgraph.qt_nodes import NODE_COLOR_FABRICATOR

        node = graph.create_node("com.craftgraph.FabricatorNode", name="Fab1")
        assert node.color() == NODE_COLOR_FABRICATOR


class TestFabricatorRegistry:
    def test_all_registry_fields_have_widgets(self, graph):
        from craftgraph.pin_registry import PinType

        node = graph.create_node("com.craftgraph.FabricatorNode", name="Fab1")
        node._maybe_build_widgets()
        for fp in node.FIELD_REGISTRY:
            if fp.pin_type == PinType.INGREDIENT_LIST:
                continue
            assert node.get_property(fp.name) is not None, f"Missing property: {fp.name}"

    def test_split_outputs_creates_typed_pins(self, graph):
        node = graph.create_node("com.craftgraph.FabricatorNode", name="Fab1")
        assert node.SPLIT_OUTPUTS is True
        for name in ("tabs_out", "added_out", "alias_out", "foods_out", "moved_out"):
            assert node.get_output(name) is not None, f"Missing output: {name}"

    def test_no_children_port_when_split(self, graph):
        node = graph.create_node("com.craftgraph.FabricatorNode", name="Fab1")
        assert node.get_output("children") is None

    def test_new_fields_present(self, graph):
        node = graph.create_node("com.craftgraph.FabricatorNode", name="Fab1")
        node._maybe_build_widgets()
        for name in (
            "tooltip",
            "color_tint",
            "allowed_in_base",
            "allowed_in_cyclops",
            "pda_group",
            "pda_category",
            "force_unlock_at_start",
            "unlocked_by",
        ):
            assert node.get_property(name) is not None, f"Missing property: {name}"

    def test_populate_from_model(self, graph):
        from craftgraph.models import CustomFabricator

        fab = CustomFabricator(
            item_id="MyFab",
            display_name="My Fabricator",
            model="Workbench",
            allowed_in_base=False,
            color_tint=[0.5, 0.3, 0.8],
        )
        node = graph.create_node("com.craftgraph.FabricatorNode", name="Fab1")
        node.model_ref = fab
        node.populate_from_model()
        assert node.get_property("item_id") == "MyFab"
        assert node.get_property("model") == "Workbench"
        assert node.get_property("color_tint") == "0.5, 0.3, 0.8"

    def test_declares_fields_from_scratch(self, graph):
        """FabricatorNode does not inherit from ModifiedRecipeNode."""
        from craftgraph.qt_nodes import FabricatorNode, ModifiedRecipeNode

        assert not issubclass(FabricatorNode, ModifiedRecipeNode)


class TestCraftingTabNode:
    def test_ports(self, graph):
        node = graph.create_node("com.craftgraph.CraftingTabNode", name="Tab1")
        assert node.get_input("parent") is not None
        assert node.get_output("children") is not None

    def test_fields_accessible(self, graph):
        node = graph.create_node("com.craftgraph.CraftingTabNode", name="Tab1")
        node._maybe_build_widgets()
        assert node.get_property("tab_id") is not None
        assert node.get_property("display_name") is not None

    def test_node_color(self, graph):
        from craftgraph.qt_nodes import NODE_COLOR_CRAFTING_TAB

        node = graph.create_node("com.craftgraph.CraftingTabNode", name="Tab1")
        assert node.color() == NODE_COLOR_CRAFTING_TAB


class TestMovedRecipeNode:
    def test_ports(self, graph):
        node = graph.create_node("com.craftgraph.MovedRecipeNode", name="M1")
        node._maybe_build_widgets()
        # 5 field_* ports (no sprite_in)
        assert node.get_input("sprite_in") is None
        assert len(node.input_ports()) == 5
        assert node.output_ports() == []

    def test_fields_accessible(self, graph):
        node = graph.create_node("com.craftgraph.MovedRecipeNode", name="M1")
        node._maybe_build_widgets()
        assert node.get_property("item_id") is not None
        assert node.get_property("old_path") is not None
        assert node.get_property("new_path") is not None
        assert node.get_property("copied") is not None
        assert node.get_property("hidden") is not None

    def test_node_color(self, graph):
        from craftgraph.qt_nodes import NODE_COLOR_MOVED_RECIPE

        node = graph.create_node("com.craftgraph.MovedRecipeNode", name="M1")
        assert node.color() == NODE_COLOR_MOVED_RECIPE


class TestCustomBioFuelNode:
    def test_ports(self, graph):
        node = graph.create_node("com.craftgraph.CustomBioFuelNode", name="BF1")
        node._maybe_build_widgets()
        # 2 field_* ports (no sprite_in)
        assert node.get_input("sprite_in") is None
        assert len(node.input_ports()) == 2
        assert node.output_ports() == []

    def test_fields_accessible(self, graph):
        node = graph.create_node("com.craftgraph.CustomBioFuelNode", name="BF1")
        node._maybe_build_widgets()
        assert node.get_property("item_id") is not None
        assert node.get_property("energy") is not None

    def test_energy_float_value(self, graph):
        node = graph.create_node("com.craftgraph.CustomBioFuelNode", name="BF1")
        node.set_property("energy", 420.0)
        assert float(node.get_property("energy")) == 420.0

    def test_node_color(self, graph):
        from craftgraph.qt_nodes import NODE_COLOR_CUSTOM_BIO_FUEL

        node = graph.create_node("com.craftgraph.CustomBioFuelNode", name="BF1")
        assert node.color() == NODE_COLOR_CUSTOM_BIO_FUEL


class TestCustomFragmentCountNode:
    def test_ports(self, graph):
        node = graph.create_node("com.craftgraph.CustomFragmentCountNode", name="FC1")
        node._maybe_build_widgets()
        # 2 field_* ports (no sprite_in)
        assert node.get_input("sprite_in") is None
        assert len(node.input_ports()) == 2
        assert node.output_ports() == []

    def test_fields_accessible(self, graph):
        node = graph.create_node("com.craftgraph.CustomFragmentCountNode", name="FC1")
        node._maybe_build_widgets()
        assert node.get_property("item_id") is not None
        assert node.get_property("fragments_to_scan") is not None

    def test_fragments_int_value(self, graph):
        node = graph.create_node("com.craftgraph.CustomFragmentCountNode", name="FC1")
        node.set_property("fragments_to_scan", 5)
        assert int(node.get_property("fragments_to_scan")) == 5

    def test_node_color(self, graph):
        from craftgraph.qt_nodes import NODE_COLOR_CUSTOM_FRAGMENT_COUNT

        node = graph.create_node("com.craftgraph.CustomFragmentCountNode", name="FC1")
        assert node.color() == NODE_COLOR_CUSTOM_FRAGMENT_COUNT


# ---------------------------------------------------------------------------
# Checkbox 4: Node registry
# ---------------------------------------------------------------------------


class TestNodeRegistry:
    def test_registry_has_all_kinds(self):
        from craftgraph.qt_nodes import NODE_REGISTRY, NodeKind

        for kind in NodeKind:
            assert kind in NODE_REGISTRY, f"{kind} missing from NODE_REGISTRY"

    def test_all_node_classes_count(self):
        from craftgraph.qt_nodes import NODE_REGISTRY, all_node_classes

        classes = all_node_classes()
        assert len(classes) == len(NODE_REGISTRY)

    def test_all_node_classes_are_unique(self):
        from craftgraph.qt_nodes import all_node_classes

        classes = all_node_classes()
        assert len(set(classes)) == len(classes)

    def test_registry_values_are_base_subclasses(self):
        from craftgraph.qt_nodes import NODE_REGISTRY, CraftGraphBaseNode

        for kind, cls in NODE_REGISTRY.items():
            assert issubclass(cls, CraftGraphBaseNode), (
                f"{kind}: {cls} not a CraftGraphBaseNode subclass"
            )

    def test_node_kind_values(self):
        from craftgraph.qt_nodes import NodeKind

        expected = {
            "ModifiedRecipe",
            "AddedRecipe",
            "AliasRecipe",
            "CustomFood",
            "Fabricator",
            "CraftingTab",
            "CustomSize",
            "MovedRecipe",
            "CustomBioFuel",
            "CustomFragmentCount",
            "OrphanIngredient",
            "Sprite",
        }
        assert {k.value for k in NodeKind} == expected


# ---------------------------------------------------------------------------
# Orphan ingredient node (Step M7.8)
# ---------------------------------------------------------------------------


class TestOrphanIngredientNode:
    def test_create_orphan_ingredient(self, graph):
        """OrphanIngredientNode can be created and has expected ports."""
        node = graph.create_node(
            "com.craftgraph.OrphanIngredientNode",
            name="OrphanTest",
        )
        assert node is not None
        assert node.get_output("output") is not None

    def test_orphan_has_grey_color(self, graph):
        """OrphanIngredientNode uses the muted grey color."""
        node = graph.create_node(
            "com.craftgraph.OrphanIngredientNode",
            name="Grey",
        )
        color = node.color()
        assert color[:3] == (90, 90, 90)

    def test_orphan_has_item_id_widget(self, graph):
        """OrphanIngredientNode exposes an item_id text input."""
        node = graph.create_node(
            "com.craftgraph.OrphanIngredientNode",
            name="Widget",
        )
        node.set_property("item_id", "Gold")
        assert node.get_property("item_id") == "Gold"

    def test_orphan_has_no_model_ref(self, graph):
        """OrphanIngredientNode starts with model_ref = None."""
        node = graph.create_node(
            "com.craftgraph.OrphanIngredientNode",
            name="NoModel",
        )
        assert node.model_ref is None

    def test_orphan_output_connects_to_recipe_ingredient(self, graph):
        """OrphanIngredientNode output can connect to a recipe ingredient port."""
        orphan = graph.create_node(
            "com.craftgraph.OrphanIngredientNode",
            name="Orphan",
        )
        recipe = graph.create_node(
            "com.craftgraph.ModifiedRecipeNode",
            name="Recipe",
        )
        out_port = orphan.get_output("output")
        in_port = recipe.get_input("ingredient_0")
        out_port.connect_to(in_port)
        assert in_port.connected_ports()


# ---------------------------------------------------------------------------
# PaintedFieldsByDefault tests
# ---------------------------------------------------------------------------


class TestPaintedFieldsByDefault:
    """Every CraftGraphBaseNode subclass uses PaintedFieldsNodeItem by default."""

    @pytest.mark.parametrize(
        "node_cls",
        [
            pytest.param("com.craftgraph.FabricatorNode", id="FabricatorNode"),
            pytest.param("com.craftgraph.CraftingTabNode", id="CraftingTabNode"),
            pytest.param("com.craftgraph.CustomSizeNode", id="CustomSizeNode"),
            pytest.param("com.craftgraph.MovedRecipeNode", id="MovedRecipeNode"),
            pytest.param("com.craftgraph.CustomBioFuelNode", id="CustomBioFuelNode"),
            pytest.param("com.craftgraph.CustomFragmentCountNode", id="CustomFragmentCountNode"),
        ],
    )
    def test_structural_node_uses_painted_fields_item(self, graph, node_cls):
        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        node = graph.create_node(node_cls, name="x")
        assert isinstance(node.view, PaintedFieldsNodeItem)

    def test_orphan_ingredient_uses_painted_fields_item(self, graph):
        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        orphan = graph.create_node("com.craftgraph.OrphanIngredientNode", name="o")
        assert isinstance(orphan.view, PaintedFieldsNodeItem)

    def test_sprite_opts_out(self, graph):
        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        sprite = graph.create_node("com.craftgraph.SpriteNode", name="s")
        assert not isinstance(sprite.view, PaintedFieldsNodeItem)


# ---------------------------------------------------------------------------
# SpriteNode tests
# ---------------------------------------------------------------------------


class TestSpriteNode:
    """Tests for the SpriteNode visual-only node type."""

    def test_create_sprite_node(self, graph):
        """SpriteNode can be created with default properties."""
        node = graph.create_node("com.craftgraph.SpriteNode", name="Sprite1")
        assert node is not None
        assert type(node).NODE_NAME == "Sprite"

    def test_sprite_node_color(self, graph):
        """SpriteNode has the gold sprite color."""
        node = graph.create_node("com.craftgraph.SpriteNode", name="Sprite1")
        color = node.color()
        assert color[:3] == (180, 160, 60)

    def test_sprite_node_has_sprite_out_port(self, graph):
        """SpriteNode has a sprite_out output port."""
        node = graph.create_node("com.craftgraph.SpriteNode", name="Sprite1")
        out_port = node.get_output("sprite_out")
        assert out_port is not None

    def test_sprite_node_has_file_path_widget(self, graph):
        """SpriteNode has a file_path text input widget."""
        node = graph.create_node("com.craftgraph.SpriteNode", name="Sprite1")
        assert node.get_property("file_path") == ""

    def test_sprite_node_no_model_ref(self, graph):
        """SpriteNode is visual-only and has no model_ref."""
        node = graph.create_node("com.craftgraph.SpriteNode", name="Sprite1")
        assert node.model_ref is None

    def test_sprite_connects_to_alias_recipe_sprite_in(self, graph):
        """SpriteNode sprite_out can connect to an AliasRecipe's sprite_in port."""
        sprite = graph.create_node("com.craftgraph.SpriteNode", name="Sprite1")
        alias = graph.create_node(
            "com.craftgraph.AliasRecipeNode",
            name="Recipe",
        )
        out_port = sprite.get_output("sprite_out")
        in_port = alias.get_input("sprite_in")
        out_port.connect_to(in_port)
        assert in_port.connected_ports()


# ---------------------------------------------------------------------------
# Checkbox 5: Port type constraints
# ---------------------------------------------------------------------------


class TestPortConstraints:
    def test_recipe_hierarchy_accepts_fabricator(self, graph):
        """Recipe hierarchy port should accept FabricatorNode.children."""
        recipe = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        hierarchy_port = recipe.get_input("hierarchy")
        accepted = recipe.accepted_port_types(hierarchy_port)
        assert "com.craftgraph.FabricatorNode" in accepted

    def test_recipe_hierarchy_accepts_tab(self, graph):
        """Recipe hierarchy port should accept CraftingTabNode.children."""
        recipe = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        hierarchy_port = recipe.get_input("hierarchy")
        accepted = recipe.accepted_port_types(hierarchy_port)
        assert "com.craftgraph.CraftingTabNode" in accepted

    def test_tab_parent_accepts_fabricator(self, graph):
        """Tab parent port should accept FabricatorNode.children."""
        tab = graph.create_node("com.craftgraph.CraftingTabNode", name="T1")
        parent_port = tab.get_input("parent")
        accepted = tab.accepted_port_types(parent_port)
        assert "com.craftgraph.FabricatorNode" in accepted

    def test_tab_parent_accepts_tab(self, graph):
        """Tab parent port should accept CraftingTabNode.children."""
        tab = graph.create_node("com.craftgraph.CraftingTabNode", name="T1")
        parent_port = tab.get_input("parent")
        accepted = tab.accepted_port_types(parent_port)
        assert "com.craftgraph.CraftingTabNode" in accepted

    def test_hierarchy_constraints_inherited_by_subclasses(self, graph):
        """AddedRecipe, AliasRecipe, CustomFood inherit hierarchy constraints."""
        subtypes = ("AddedRecipeNode", "AliasRecipeNode", "CustomFoodNode")
        for node_type in subtypes:
            node = graph.create_node(
                f"com.craftgraph.{node_type}",
                name=f"T_{node_type}",
            )
            port = node.get_input("hierarchy")
            accepted = node.accepted_port_types(port)
            assert "com.craftgraph.FabricatorNode" in accepted, (
                f"{node_type} missing FabricatorNode"
            )
            assert "com.craftgraph.CraftingTabNode" in accepted, (
                f"{node_type} missing CraftingTabNode"
            )

    def test_fab_to_recipe_hierarchy_connection(self, graph):
        """Fabricator typed output -> Recipe hierarchy connection should succeed."""
        fab = graph.create_node("com.craftgraph.FabricatorNode", name="Fab")
        recipe = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        fab.get_output("added_out").connect_to(recipe.get_input("hierarchy"))
        assert len(recipe.get_input("hierarchy").connected_ports()) == 1

    def test_tab_to_recipe_hierarchy_connection(self, graph):
        """Tab -> Recipe hierarchy connection should succeed."""
        tab = graph.create_node("com.craftgraph.CraftingTabNode", name="T1")
        recipe = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        tab.get_output("children").connect_to(recipe.get_input("hierarchy"))
        assert len(recipe.get_input("hierarchy").connected_ports()) == 1

    def test_fab_to_tab_hierarchy_connection(self, graph):
        """Fabricator tabs_out -> Tab parent connection should succeed."""
        fab = graph.create_node("com.craftgraph.FabricatorNode", name="Fab")
        tab = graph.create_node("com.craftgraph.CraftingTabNode", name="T1")
        fab.get_output("tabs_out").connect_to(tab.get_input("parent"))
        assert len(tab.get_input("parent").connected_ports()) == 1


# ---------------------------------------------------------------------------
# Cross-cutting: serialization roundtrip
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_serialize_all_node_types(self, graph):
        """Every node type should serialize without error."""
        from craftgraph.qt_nodes import NODE_REGISTRY, NodeKind

        for kind in NodeKind:
            cls = NODE_REGISTRY[kind]
            graph.create_node(cls.type_, name=f"test_{kind.value}")

        data = graph.serialize_session()
        assert len(data.get("nodes", {})) == len(NodeKind)


# ---------------------------------------------------------------------------
# Widget property roundtrip
# ---------------------------------------------------------------------------


class TestWidgetProperties:
    def test_recipe_item_id_set_get(self, graph):
        # Painted-fields path: ModifiedRecipeNode stores values as properties only.
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        node.set_property("item_id", "Titanium")
        assert node.get_property("item_id") == "Titanium"

    def test_recipe_amount_set_get(self, graph):
        """Painted-fields path: int values stored as-is on the property store."""
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        node.set_property("amount_crafted", "5")
        assert node.get_property("amount_crafted") == "5"

    def test_fab_model_set_get(self, graph):
        node = graph.create_node("com.craftgraph.FabricatorNode", name="Fab1")
        node.set_property("model", "Workbench")
        assert node.get_property("model") == "Workbench"

    def test_tab_id_set_get(self, graph):
        node = graph.create_node("com.craftgraph.CraftingTabNode", name="T1")
        node.set_property("tab_id", "Weapons")
        assert node.get_property("tab_id") == "Weapons"


# ---------------------------------------------------------------------------
# Sprite support
# ---------------------------------------------------------------------------

_SPRITE_PATH = (
    Path(__file__).parent.parent
    / "craftgraph"
    / "cc3_reference_files"
    / "real-mod-examples"
    / "Assets"
    / "Alch_Fab.png"
)


class TestSpriteSupport:
    def test_set_sprite_stores_path(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode")
        if not _SPRITE_PATH.exists():
            pytest.skip("Reference sprite not found")
        node.set_sprite(_SPRITE_PATH)
        assert node.sprite_path == _SPRITE_PATH

    def test_set_sprite_sets_pixmap(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode")
        if not _SPRITE_PATH.exists():
            pytest.skip("Reference sprite not found")
        node.set_sprite(_SPRITE_PATH)
        pixmap = node.view._icon_item.pixmap()
        assert not pixmap.isNull()
        assert pixmap.height() == 64

    def test_clear_sprite_resets(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode")
        if not _SPRITE_PATH.exists():
            pytest.skip("Reference sprite not found")
        node.set_sprite(_SPRITE_PATH)
        node.clear_sprite()
        assert node.sprite_path is None

    def test_set_sprite_none_clears(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode")
        node.set_sprite(None)
        assert node.sprite_path is None

    def test_set_sprite_nonexistent_path_ignored(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode")
        node.set_sprite(Path("/nonexistent/sprite.png"))
        assert node.sprite_path is None


# ---------------------------------------------------------------------------
# Task 7: CraftingTab + utility node FIELD_REGISTRY tests
# ---------------------------------------------------------------------------


class TestCraftingTabRegistry:
    def test_all_fields_have_widgets(self, graph):
        from craftgraph.pin_registry import PinType

        node = graph.create_node("com.craftgraph.CraftingTabNode", name="T1")
        node._maybe_build_widgets()
        for fp in node.FIELD_REGISTRY:
            if fp.pin_type == PinType.INGREDIENT_LIST:
                continue
            assert node.get_property(fp.name) is not None, f"Missing property: {fp.name}"

    def test_parent_port_still_exists(self, graph):
        node = graph.create_node("com.craftgraph.CraftingTabNode", name="T1")
        assert node.get_input("parent") is not None

    def test_children_output_exists(self, graph):
        node = graph.create_node("com.craftgraph.CraftingTabNode", name="T1")
        assert node.get_output("children") is not None

    def test_sprite_item_id_nullable(self, graph):
        from craftgraph.models import CraftingTab

        tab = CraftingTab(tab_id="Weapons", sprite_item_id=None)
        node = graph.create_node("com.craftgraph.CraftingTabNode", name="T1")
        node.model_ref = tab
        node.populate_from_model()
        assert node.get_property("sprite_item_id") == ""


class TestCustomSizeRegistry:
    def test_model_field_remapping(self, graph):
        from craftgraph.models import CustomSize

        size = CustomSize(item_id="Titanium", width=3, height=2)
        node = graph.create_node("com.craftgraph.CustomSizeNode", name="S1")
        node.model_ref = size
        node.populate_from_model()
        assert int(node.get_property("size_width")) == 3
        assert int(node.get_property("size_height")) == 2


class TestMovedRecipeRegistry:
    def test_nullable_paths(self, graph):
        from craftgraph.models import MovedRecipe

        moved = MovedRecipe(item_id="Knife", old_path=None, new_path="Fab/Tools")
        node = graph.create_node("com.craftgraph.MovedRecipeNode", name="M1")
        node.model_ref = moved
        node.populate_from_model()
        assert node.get_property("old_path") == ""
        assert node.get_property("new_path") == "Fab/Tools"


class TestUtilityNodeRegistries:
    """Spot-check that CustomBioFuel and CustomFragmentCount have registries."""

    def test_biofuel_populate(self, graph):
        from craftgraph.models import CustomBioFuel

        fuel = CustomBioFuel(item_id="CreepvinePiece", energy=420.0)
        node = graph.create_node("com.craftgraph.CustomBioFuelNode", name="BF1")
        node.model_ref = fuel
        node.populate_from_model()
        assert float(node.get_property("energy")) == 420.0

    def test_fragment_populate(self, graph):
        from craftgraph.models import CustomFragmentCount

        frag = CustomFragmentCount(item_id="SeamothFragment", fragments_to_scan=5)
        node = graph.create_node("com.craftgraph.CustomFragmentCountNode", name="FC1")
        node.model_ref = frag
        node.populate_from_model()
        assert int(node.get_property("fragments_to_scan")) == 5


class TestWidgetZOrder:
    def test_widget_z_values_descend(self, graph):
        """Proxy widgets should have descending z-values (topmost highest).

        Uses SpriteNode -- the only node that still carries embedded Qt
        widgets (text input + Browse button) now that all data-model nodes
        are on the painted-fields path.
        """
        node = graph.create_node("com.craftgraph.SpriteNode", name="Sprite")
        node._maybe_build_widgets()
        widgets = list(node.view.widgets.values())
        assert len(widgets) >= 1
        z_values = [w.zValue() for w in widgets]
        for i in range(len(z_values) - 1):
            assert z_values[i] > z_values[i + 1], (
                f"widget {i} z={z_values[i]} should be > widget {i + 1} z={z_values[i + 1]}"
            )

    def test_first_widget_above_z_val_node_widget(self, graph):
        """First widget z-value should be above the base Z_VAL_NODE_WIDGET."""
        from NodeGraphQt.constants import Z_VAL_NODE_WIDGET

        node = graph.create_node("com.craftgraph.SpriteNode", name="Test")
        node._maybe_build_widgets()
        widgets = list(node.view.widgets.values())
        assert len(widgets) > 0
        assert widgets[0].zValue() > Z_VAL_NODE_WIDGET


# ---------------------------------------------------------------------------
# Overflow tooltips (Task 2)
# ---------------------------------------------------------------------------


class TestOverflowTooltips:
    """Node field widgets update their tooltip to the current text value."""

    def test_text_field_tooltip_updates_on_change(self, graph):
        """Text input tooltip tracks the current text value.

        Uses SpriteNode (legacy widget path) since painted nodes do not
        carry embedded Qt widgets.
        """
        from PySide6.QtWidgets import QLineEdit

        node = graph.create_node("com.craftgraph.SpriteNode", name="Test")
        node._maybe_build_widgets()
        widget_item = node.get_widget("file_path")
        assert widget_item is not None
        qt_widget = widget_item.get_custom_widget()
        assert isinstance(qt_widget, QLineEdit)
        qt_widget.setText("Titanium")
        assert qt_widget.toolTip() == "Titanium"


# ---------------------------------------------------------------------------
# Step 11g.2: Enhanced SpriteNode -- file picker, preview, drag-drop
# ---------------------------------------------------------------------------


class TestSpriteNodeSelfPreview:
    """Setting file_path on a SpriteNode updates its header icon."""

    def test_setting_file_path_triggers_self_preview(self, graph):
        """Setting file_path to a valid PNG sets the sprite on itself."""
        if not _SPRITE_PATH.exists():
            pytest.skip("Reference sprite not found")
        node = graph.create_node("com.craftgraph.SpriteNode", name="S1")
        node._maybe_build_widgets()
        node.set_property("file_path", str(_SPRITE_PATH))
        assert node.sprite_path == _SPRITE_PATH
        pixmap = node.view._icon_item.pixmap()
        assert not pixmap.isNull()

    def test_clearing_file_path_clears_preview(self, graph):
        """Clearing file_path removes the self-preview sprite."""
        if not _SPRITE_PATH.exists():
            pytest.skip("Reference sprite not found")
        node = graph.create_node("com.craftgraph.SpriteNode", name="S1")
        node._maybe_build_widgets()
        node.set_property("file_path", str(_SPRITE_PATH))
        assert node.sprite_path is not None
        node.set_property("file_path", "")
        assert node.sprite_path is None

    def test_invalid_path_clears_preview(self, graph):
        """Setting a nonexistent path clears the sprite."""
        node = graph.create_node("com.craftgraph.SpriteNode", name="S1")
        node.set_property("file_path", "/nonexistent/fake.png")
        assert node.sprite_path is None


class TestSpriteNodeBrowseButton:
    """SpriteNode has a Browse button widget."""

    def test_browse_button_exists(self, graph):
        """SpriteNode has a browse_file widget."""
        node = graph.create_node("com.craftgraph.SpriteNode", name="S1")
        widget_item = node.get_widget("browse_file")
        assert widget_item is not None

    def test_browse_button_is_pushbutton(self, graph):
        """The browse widget contains a QPushButton."""
        from PySide6.QtWidgets import QPushButton

        node = graph.create_node("com.craftgraph.SpriteNode", name="S1")
        widget_item = node.get_widget("browse_file")
        inner = widget_item.get_custom_widget()
        # The custom widget itself or a child should be a QPushButton
        found = inner.findChild(QPushButton) if not isinstance(inner, QPushButton) else inner
        assert found is not None


    def test_browse_widget_can_access_parent_node(self, graph):
        """The browse widget's .node property returns the SpriteNode."""
        node = graph.create_node("com.craftgraph.SpriteNode", name="S1")
        browse_widget = node.get_widget("browse_file")
        # NodeBaseWidget.node should point back to the owning SpriteNode
        assert browse_widget.node is node

    def test_open_dialog_sets_file_path_on_node(self, graph, tmp_path):
        """Selecting a file in the browse dialog sets the node's file_path."""
        from unittest.mock import patch

        node = graph.create_node("com.craftgraph.SpriteNode", name="S1")
        browse_widget = node.get_widget("browse_file")

        fake_png = tmp_path / "sprite.png"
        fake_png.write_bytes(b"fake")

        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=(str(fake_png), "PNG Files (*.png)"),
        ):
            browse_widget._open_dialog()

        assert node.get_property("file_path") == str(fake_png)


class TestSpriteNodePropagation:
    """SpriteNode file_path changes propagate to connected target nodes."""

    def test_file_path_change_propagates_to_connected_node(self, graph):
        """Changing file_path on SpriteNode sets sprite on connected node."""
        if not _SPRITE_PATH.exists():
            pytest.skip("Reference sprite not found")
        sprite = graph.create_node("com.craftgraph.SpriteNode", name="S1")
        alias = graph.create_node("com.craftgraph.AliasRecipeNode")
        alias._maybe_build_widgets()
        out_port = sprite.get_output("sprite_out")
        in_port = alias.get_input("sprite_in")
        out_port.connect_to(in_port)

        # Simulate browsing: set file_path after connection
        sprite.set_property("file_path", str(_SPRITE_PATH))

        assert alias.sprite_path == _SPRITE_PATH

    def test_clearing_file_path_clears_connected_node(self, graph):
        """Clearing file_path on SpriteNode clears sprite on connected node."""
        if not _SPRITE_PATH.exists():
            pytest.skip("Reference sprite not found")
        sprite = graph.create_node("com.craftgraph.SpriteNode", name="S1")
        alias = graph.create_node("com.craftgraph.AliasRecipeNode")
        alias._maybe_build_widgets()
        out_port = sprite.get_output("sprite_out")
        in_port = alias.get_input("sprite_in")
        out_port.connect_to(in_port)

        sprite.set_property("file_path", str(_SPRITE_PATH))
        assert alias.sprite_path is not None

        sprite.set_property("file_path", "")
        assert alias.sprite_path is None

    def test_file_path_propagates_to_multiple_nodes(self, graph):
        """SpriteNode propagates to all connected nodes (multi-output)."""
        if not _SPRITE_PATH.exists():
            pytest.skip("Reference sprite not found")
        sprite = graph.create_node("com.craftgraph.SpriteNode", name="S1")
        alias = graph.create_node("com.craftgraph.AliasRecipeNode")
        alias._maybe_build_widgets()
        tab = graph.create_node("com.craftgraph.CraftingTabNode")
        tab._maybe_build_widgets()
        out_port = sprite.get_output("sprite_out")
        out_port.connect_to(alias.get_input("sprite_in"))
        out_port.connect_to(tab.get_input("sprite_in"))

        sprite.set_property("file_path", str(_SPRITE_PATH))

        assert alias.sprite_path == _SPRITE_PATH
        assert tab.sprite_path == _SPRITE_PATH

    def test_no_propagation_when_no_connections(self, graph):
        """Changing file_path with no connections does not raise."""
        sprite = graph.create_node("com.craftgraph.SpriteNode", name="S1")
        # Should not raise even with no connections
        sprite.set_property("file_path", "/some/path.png")
        sprite.set_property("file_path", "")

    def test_sprite_item_id_set_on_alias_recipe(self, graph):
        """SpriteNode sets sprite_item_id on AliasRecipe from PNG filename stem."""
        if not _SPRITE_PATH.exists():
            pytest.skip("Reference sprite not found")
        sprite = graph.create_node("com.craftgraph.SpriteNode", name="S1")
        alias = graph.create_node("com.craftgraph.AliasRecipeNode")
        alias._maybe_build_widgets()
        out_port = sprite.get_output("sprite_out")
        out_port.connect_to(alias.get_input("sprite_in"))

        sprite.set_property("file_path", str(_SPRITE_PATH))

        assert alias.get_property("sprite_item_id") == _SPRITE_PATH.stem

    def test_sprite_item_id_set_on_crafting_tab(self, graph):
        """SpriteNode sets sprite_item_id on CraftingTab from PNG filename stem."""
        if not _SPRITE_PATH.exists():
            pytest.skip("Reference sprite not found")
        sprite = graph.create_node("com.craftgraph.SpriteNode", name="S1")
        tab = graph.create_node("com.craftgraph.CraftingTabNode")
        tab._maybe_build_widgets()
        out_port = sprite.get_output("sprite_out")
        out_port.connect_to(tab.get_input("sprite_in"))

        sprite.set_property("file_path", str(_SPRITE_PATH))

        assert tab.get_property("sprite_item_id") == _SPRITE_PATH.stem

    def test_clearing_sprite_clears_sprite_item_id(self, graph):
        """Clearing file_path resets sprite_item_id to empty string."""
        if not _SPRITE_PATH.exists():
            pytest.skip("Reference sprite not found")
        sprite = graph.create_node("com.craftgraph.SpriteNode", name="S1")
        alias = graph.create_node("com.craftgraph.AliasRecipeNode")
        alias._maybe_build_widgets()
        out_port = sprite.get_output("sprite_out")
        out_port.connect_to(alias.get_input("sprite_in"))

        sprite.set_property("file_path", str(_SPRITE_PATH))
        assert alias.get_property("sprite_item_id") == _SPRITE_PATH.stem

        sprite.set_property("file_path", "")
        assert alias.get_property("sprite_item_id") == ""


class TestViewerDragDropFilter:
    """Drag-drop event filter for the NodeGraphQt viewer."""

    def _make_drag_enter(self, urls):
        """Create a (QDragEnterEvent, QMimeData) for the given file URLs.

        Returns a tuple so the caller keeps a reference to the QMimeData,
        preventing premature GC of the underlying C++ object.
        """
        from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
        from PySide6.QtGui import QDragEnterEvent

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(u)) for u in urls])
        event = QDragEnterEvent(
            QPoint(100, 100),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        return event, mime

    def _make_drop(self, urls, pos=None):
        """Create a (QDropEvent, QMimeData) for the given file URLs."""
        from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
        from PySide6.QtGui import QDropEvent

        if pos is None:
            pos = QPointF(100.0, 100.0)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(u)) for u in urls])
        event = QDropEvent(
            pos,
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        return event, mime

    def test_accepts_png_drag(self, graph):
        """Drag with a .png URL is accepted (eventFilter returns True)."""
        from craftgraph.qt_gui import _ViewerDropFilter

        viewer = graph.viewer()
        filt = _ViewerDropFilter(viewer, window=None)
        event, _mime = self._make_drag_enter(["/some/image.png"])
        result = filt.eventFilter(viewer, event)
        assert result is True

    def test_rejects_non_png_drag(self, graph):
        """Drag with a non-.png URL is not handled by the filter."""
        from craftgraph.qt_gui import _ViewerDropFilter

        viewer = graph.viewer()
        filt = _ViewerDropFilter(viewer, window=None)
        event, _mime = self._make_drag_enter(["/some/file.txt"])
        result = filt.eventFilter(viewer, event)
        assert result is False

    def test_rejects_drag_with_no_urls(self, graph):
        """Drag with no file URLs is not intercepted."""
        from PySide6.QtCore import QMimeData, QPoint, Qt
        from PySide6.QtGui import QDragEnterEvent

        from craftgraph.qt_gui import _ViewerDropFilter

        viewer = graph.viewer()
        filt = _ViewerDropFilter(viewer, window=None)
        mime = QMimeData()
        mime.setText("just text")
        event = QDragEnterEvent(
            QPoint(100, 100),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        result = filt.eventFilter(viewer, event)
        assert result is False

    def test_accepts_png_case_insensitive(self, graph):
        """Drag with .PNG (uppercase) is also accepted."""
        from craftgraph.qt_gui import _ViewerDropFilter

        viewer = graph.viewer()
        filt = _ViewerDropFilter(viewer, window=None)
        event, _mime = self._make_drag_enter(["/some/IMAGE.PNG"])
        result = filt.eventFilter(viewer, event)
        assert result is True


class TestLivePipeViewportUpdateMode:
    """Live drag should switch the viewport to FullViewportUpdate to clear ghost arrows."""

    def _begin_drag(self, graph, viewer):
        from PySide6.QtCore import QPoint

        viewer._origin_pos = QPoint(0, 0)
        port = self._first_port(graph)
        viewer.start_live_connection(port)

    def test_starts_in_full_update_mode_during_drag(self, graph):
        from PySide6.QtWidgets import QGraphicsView

        viewer = graph.viewer()
        viewer.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self._begin_drag(graph, viewer)
        try:
            assert (
                viewer.viewportUpdateMode()
                == QGraphicsView.ViewportUpdateMode.FullViewportUpdate
            )
        finally:
            viewer.end_live_connection()

    def test_restores_previous_mode_after_drag(self, graph):
        from PySide6.QtWidgets import QGraphicsView

        viewer = graph.viewer()
        viewer.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self._begin_drag(graph, viewer)
        viewer.end_live_connection()
        assert (
            viewer.viewportUpdateMode()
            == QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate
        )

    def test_handles_smart_update_mode(self, graph):
        """A non-default starting mode is also restored verbatim."""
        from PySide6.QtWidgets import QGraphicsView

        viewer = graph.viewer()
        viewer.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self._begin_drag(graph, viewer)
        viewer.end_live_connection()
        assert (
            viewer.viewportUpdateMode()
            == QGraphicsView.ViewportUpdateMode.SmartViewportUpdate
        )

    @staticmethod
    def _first_port(graph):
        """Spawn a node and return one of its input/output ports."""
        from craftgraph.qt_nodes import IDENTIFIER

        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        # Prefer the output port (live connections normally start from outputs).
        ports = node.output_ports() or node.input_ports()
        assert ports, "expected at least one port on a ModifiedRecipeNode"
        return ports[0].view



# ---------------------------------------------------------------------------
# Decoration overlay item caching
# ---------------------------------------------------------------------------


class TestDecorationOverlayCache:
    """Decoration overlays use ItemCoordinateCache to skip repaint churn."""

    def test_warning_overlay_uses_item_coordinate_cache(self, qapp):
        from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

        from craftgraph.qt_nodes import _WarningOverlay

        # Parent must outlive the overlay; QGraphicsRectItem is a cheap stand-in.
        parent = QGraphicsRectItem()
        overlay = _WarningOverlay(parent)
        assert overlay.cacheMode() == QGraphicsItem.CacheMode.ItemCoordinateCache


# ---------------------------------------------------------------------------
# Cached pixmap renderer
# ---------------------------------------------------------------------------


class TestRenderSpritePixmapCache:
    """_render_sprite_pixmap memoizes by (path, size) so repeat calls are free."""

    def test_repeated_render_returns_cached_pixmap(self, qapp, tmp_path):
        from PySide6.QtGui import QImage

        from craftgraph.qt_nodes import _render_sprite_pixmap

        # Write a real PNG so QPixmap actually decodes something.
        png = tmp_path / "icon.png"
        QImage(8, 8, QImage.Format.Format_RGB32).save(str(png), "PNG")
        assert png.exists()

        # Reset cache so this test starts clean even if other tests pre-warmed it.
        _render_sprite_pixmap.cache_clear()

        a = _render_sprite_pixmap(png, 32)
        b = _render_sprite_pixmap(png, 32)

        info = _render_sprite_pixmap.cache_info()
        assert info.hits >= 1, f"expected cache hit on second call, got {info}"
        # Same cached object identity proves no rerender.
        assert a is b


# ---------------------------------------------------------------------------
# Phase 2 Task 4: setStyleSheet cache (skip no-op restyles)
# ---------------------------------------------------------------------------


class TestStyleSheetCache:
    """Repeated setStyleSheet with the same string is a no-op after caching."""

    def test_setstylesheet_skips_when_unchanged(self, qapp):
        from PySide6 import QtWidgets

        from craftgraph.qt_nodes import _install_stylesheet_cache

        # Use a Python subclass so we can patch the class-level method
        # without touching the C++ QLabel binding.
        class SpyLabel(QtWidgets.QLabel):
            pass

        widget = SpyLabel()
        _install_stylesheet_cache(widget)

        widget.setStyleSheet("background: red;")
        widget.setStyleSheet("background: red;")

        assert widget._cg_last_stylesheet == "background: red;"

        # Replace the class-level setStyleSheet with a counting spy and
        # verify the cache short-circuits identical follow-up calls.
        calls: list[str] = []
        original = SpyLabel.setStyleSheet

        def counting(self, sheet, _orig=original):
            calls.append(sheet)
            _orig(self, sheet)

        SpyLabel.setStyleSheet = counting  # type: ignore[assignment]
        try:
            _install_stylesheet_cache(widget)
            widget.setStyleSheet("background: red;")
            widget.setStyleSheet("background: blue;")
            assert calls == ["background: blue;"]
        finally:
            SpyLabel.setStyleSheet = original  # type: ignore[assignment]

    def test_class_level_cache_is_installed_once_and_short_circuits(self, qapp):
        """_install_stylesheet_cache_on_class patches the class once.

        The production path (``_install_stylesheet_cache_on_class(_NodeGroupBox)``
        at module load) replaces every per-instance closure with a single
        class-level descriptor swap. Verifies the sentinel idempotency and
        that the cache short-circuits identical follow-up calls.
        """
        from PySide6 import QtWidgets

        from craftgraph.qt_nodes import _install_stylesheet_cache_on_class

        class CachedLabel(QtWidgets.QLabel):
            pass

        _install_stylesheet_cache_on_class(CachedLabel)
        assert CachedLabel._cg_stylesheet_cache_installed is True

        # Calling install twice should be a no-op (sentinel guard).
        first_setter = CachedLabel.setStyleSheet
        _install_stylesheet_cache_on_class(CachedLabel)
        assert CachedLabel.setStyleSheet is first_setter

        widget = CachedLabel()
        widget.setStyleSheet("color: red;")
        assert widget._cg_last_stylesheet == "color: red;"
        # Second identical call short-circuits before touching Qt.
        widget.setStyleSheet("color: red;")
        assert widget._cg_last_stylesheet == "color: red;"
        # Different value updates the cache.
        widget.setStyleSheet("color: blue;")
        assert widget._cg_last_stylesheet == "color: blue;"


# ---------------------------------------------------------------------------
# Paint timing wired via class-level NodeItem.paint wrap
# ---------------------------------------------------------------------------


class TestPaintTimingWiring:
    """NodeItem.paint records per-class timing via perf_diag.record_paint."""

    def test_view_carries_node_class_name(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER

        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        assert getattr(node.view, "_cg_node_class_name", None) == "ModifiedRecipeNode"

    def test_paint_records_into_perf_diag(self, qapp, graph):
        from PySide6.QtGui import QPainter, QPixmap
        from PySide6.QtWidgets import QStyleOptionGraphicsItem

        from craftgraph import perf_diag
        from craftgraph.qt_nodes import IDENTIFIER

        perf_diag.reset_paint_stats()
        perf_diag.set_paint_recording(True)
        try:
            node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
            pixmap = QPixmap(200, 200)
            painter = QPainter(pixmap)
            try:
                opt = QStyleOptionGraphicsItem()
                node.view.paint(painter, opt, None)
            finally:
                painter.end()

            stats = perf_diag.paint_stats()
            assert "ModifiedRecipeNode" in stats
            assert stats["ModifiedRecipeNode"].count >= 1
            assert stats["ModifiedRecipeNode"].total_ms >= 0.0
        finally:
            perf_diag.set_paint_recording(False)
            perf_diag.reset_paint_stats()

    def test_paint_does_not_record_when_disabled(self, qapp, graph):
        from PySide6.QtGui import QPainter, QPixmap
        from PySide6.QtWidgets import QStyleOptionGraphicsItem

        from craftgraph import perf_diag
        from craftgraph.qt_nodes import IDENTIFIER

        perf_diag.reset_paint_stats()
        perf_diag.set_paint_recording(False)

        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        pixmap = QPixmap(200, 200)
        painter = QPainter(pixmap)
        try:
            opt = QStyleOptionGraphicsItem()
            node.view.paint(painter, opt, None)
        finally:
            painter.end()

        assert perf_diag.paint_stats() == {}


# ---------------------------------------------------------------------------
# PortItem.boundingRect caching
# ---------------------------------------------------------------------------


class TestPortBoundingRectCache:
    """PortItem.boundingRect returns a cached QRectF since _width/_height never change."""

    def test_returns_same_instance_on_repeat_call(self, qapp, graph):
        from craftgraph.qt_nodes import IDENTIFIER

        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        ports = node.view.inputs + node.view.outputs
        assert ports, "expected at least one port on a recipe node"
        port = ports[0]
        first = port.boundingRect()
        second = port.boundingRect()
        assert first is second

    def test_cache_matches_original_dimensions(self, qapp, graph):
        from NodeGraphQt.constants import PortEnum

        from craftgraph.qt_nodes import IDENTIFIER

        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        ports = node.view.inputs + node.view.outputs
        port = ports[0]
        rect = port.boundingRect()
        # PortEnum.SIZE + CLICK_FALLOFF was the original formula.
        expected_w = PortEnum.SIZE.value + PortEnum.CLICK_FALLOFF.value
        expected_h = PortEnum.SIZE.value
        assert rect.width() == expected_w
        assert rect.height() == expected_h

    def test_cache_is_per_instance(self, qapp, graph):
        from craftgraph.qt_nodes import IDENTIFIER

        node_a = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        node_b = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        port_a = (node_a.view.inputs + node_a.view.outputs)[0]
        port_b = (node_b.view.inputs + node_b.view.outputs)[0]
        # Same dimensions but distinct cached objects -- caller must not be
        # able to mutate one port's rect and affect another.
        assert port_a.boundingRect() is not port_b.boundingRect()


class TestLazyWidgetBuild:
    def test_widgets_not_built_on_create(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER
        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        assert node._cg_widgets_pending is True

    def test_widgets_built_on_first_paint(self, qapp, graph):
        from PySide6.QtGui import QPainter
        from PySide6.QtWidgets import QStyleOptionGraphicsItem
        from craftgraph.qt_nodes import IDENTIFIER
        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        opt = QStyleOptionGraphicsItem()
        # painting into a null QPainter does nothing, but the patch fires.
        node.view.paint(QPainter(), opt, None)
        assert node._cg_widgets_pending is False

    def test_paint_patch_is_class_level_idempotent(self, qapp, graph):
        from craftgraph.qt_nodes import IDENTIFIER
        # Two separate nodes share the same patched paint -- not per-instance.
        n1 = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        n2 = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        assert type(n1.view).paint is type(n2.view).paint
        # Sentinel set on the class.
        assert getattr(type(n1.view), "_cg_lazy_build_patched", False) is True


class TestLazyPopulate:
    def test_populate_before_paint_defers(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER
        from craftgraph.models import ModifiedRecipe

        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        node.model_ref = ModifiedRecipe(item_id="Titanium", amount_crafted=5)
        node.populate_from_model()
        # Widgets still pending; populate marked as deferred.
        assert node._cg_widgets_pending is True
        assert node._cg_pending_populate is True

    def test_paint_replays_deferred_populate(self, qapp, graph):
        from PySide6.QtGui import QPainter
        from PySide6.QtWidgets import QStyleOptionGraphicsItem
        from craftgraph.qt_nodes import IDENTIFIER
        from craftgraph.models import ModifiedRecipe

        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        node.model_ref = ModifiedRecipe(item_id="Titanium", amount_crafted=5)
        node.populate_from_model()

        opt = QStyleOptionGraphicsItem()
        node.view.paint(QPainter(), opt, None)

        # Widgets exist now AND the model values landed (not defaults).
        assert node._cg_widgets_pending is False
        assert int(node.get_property("amount_crafted")) == 5


class TestLazyPropertyAccess:
    def test_get_property_triggers_build(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER
        from craftgraph.models import ModifiedRecipe

        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        node.model_ref = ModifiedRecipe(item_id="Titanium", amount_crafted=7)
        node.populate_from_model()
        # No paint, but reading should still see the populated value.
        assert int(node.get_property("amount_crafted")) == 7
        assert node._cg_widgets_pending is False

    def test_set_property_triggers_build(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER
        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        node.set_property("amount_crafted", "3")
        assert node._cg_widgets_pending is False
        assert int(node.get_property("amount_crafted")) == 3


class TestPaintedFieldsNodeItem:
    """Verify PaintedFieldsNodeItem behavior on every recipe subclass's view."""

    @pytest.mark.parametrize(
        "class_name",
        [
            "ModifiedRecipeNode",
            "AddedRecipeNode",
            "AliasRecipeNode",
            "CustomFoodNode",
            "FabricatorNode",
            "CraftingTabNode",
            "CustomSizeNode",
            "MovedRecipeNode",
            "CustomBioFuelNode",
            "CustomFragmentCountNode",
        ],
    )
    def test_view_is_painted_item(self, qapp, graph, class_name):
        from craftgraph.qt_nodes import IDENTIFIER, PaintedFieldsNodeItem

        node = graph.create_node(f"{IDENTIFIER}.{class_name}")
        assert isinstance(node.view, PaintedFieldsNodeItem)

    @pytest.mark.parametrize(
        "class_name",
        [
            "ModifiedRecipeNode",
            "AddedRecipeNode",
            "AliasRecipeNode",
            "CustomFoodNode",
            "FabricatorNode",
            "CraftingTabNode",
            "CustomSizeNode",
            "MovedRecipeNode",
            "CustomBioFuelNode",
            "CustomFragmentCountNode",
        ],
    )
    def test_bounding_rect_grows_with_fields(self, qapp, graph, class_name):
        from craftgraph.qt_nodes import IDENTIFIER

        node = graph.create_node(f"{IDENTIFIER}.{class_name}")
        node._maybe_build_widgets()
        br = node.view.boundingRect()
        # Each painted row is at least 22 px high; subclasses have more rows.
        assert br.height() >= 22.0 * max(1, len(node.view._cg_field_rects))

    def test_field_at_returns_hit_field(self, qapp, graph):
        """Hit-test smoke check (independent of class -- uses a synthetic rect list)."""
        from PySide6.QtCore import QPointF, QRectF

        from craftgraph.painted_fields import FieldRect, FieldState
        from craftgraph.pin_registry import PinType
        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        item = PaintedFieldsNodeItem(name="test_node")
        item._cg_field_rects = [
            FieldRect(
                name="amount",
                pin_type=PinType.INT,
                label_rect=None,
                value_rect=QRectF(50, 0, 100, 22),
                state=FieldState.NORMAL,
            )
        ]
        item._cg_hit_rects = {"amount": QRectF(0, 0, 150, 22)}
        hit = item._field_at(QPointF(75, 10))
        assert hit is not None
        assert hit.name == "amount"
        miss = item._field_at(QPointF(500, 500))
        assert miss is None


class TestModifiedRecipeNoWidgets:
    """Verify painted-field nodes build no QWidgets for their registry."""

    NODE_CLASSES = (
        ("ModifiedRecipeNode", ("item_id", "amount_crafted", "linked_item_ids",
                                "unlocks", "unlocked_by", "force_unlock_at_start")),
        ("AddedRecipeNode", ("item_id", "amount_crafted", "linked_item_ids",
                             "unlocks", "unlocked_by", "force_unlock_at_start",
                             "path", "pda_group", "pda_category")),
        ("AliasRecipeNode", ("item_id", "amount_crafted", "linked_item_ids",
                             "unlocks", "unlocked_by", "force_unlock_at_start",
                             "path", "pda_group", "pda_category",
                             "display_name", "tooltip", "functional_id",
                             "sprite_item_id")),
        ("CustomFoodNode", ("item_id", "amount_crafted", "linked_item_ids",
                            "unlocks", "unlocked_by", "force_unlock_at_start",
                            "path", "pda_group", "pda_category",
                            "display_name", "tooltip", "functional_id",
                            "sprite_item_id",
                            "food_value", "water_value", "oxygen_value",
                            "health_value", "decay_rate_mod", "food_type",
                            "use_drink_sound")),
        # Structural nodes (no QWidget expected for any painted field)
        ("FabricatorNode", ("item_id", "display_name", "tooltip", "model",
                            "color_tint", "allowed_in_base", "allowed_in_cyclops",
                            "pda_group", "pda_category", "force_unlock_at_start",
                            "unlocked_by")),
        ("CraftingTabNode", ("tab_id", "display_name", "sprite_item_id", "parent_tab_path")),
        ("CustomSizeNode", ("item_id", "size_width", "size_height")),
        ("MovedRecipeNode", ("item_id", "old_path", "new_path", "copied", "hidden")),
        ("CustomBioFuelNode", ("item_id", "energy")),
        ("CustomFragmentCountNode", ("item_id", "fragments_to_scan")),
    )

    @pytest.mark.parametrize("class_name,field_names", NODE_CLASSES)
    def test_no_qline_edits_built(self, graph, class_name, field_names):
        from craftgraph.qt_nodes import IDENTIFIER

        node = graph.create_node(f"{IDENTIFIER}.{class_name}")
        node._maybe_build_widgets()
        for name in field_names:
            assert node.get_widget(name) is None, f"{class_name}: widget exists for {name}"

    @pytest.mark.parametrize("class_name", [c[0] for c in NODE_CLASSES])
    def test_view_is_painted_node_item(self, graph, class_name):
        from craftgraph.qt_nodes import IDENTIFIER, PaintedFieldsNodeItem

        node = graph.create_node(f"{IDENTIFIER}.{class_name}")
        assert isinstance(node.view, PaintedFieldsNodeItem)

    @pytest.mark.parametrize("class_name", [c[0] for c in NODE_CLASSES])
    def test_field_rects_populated_after_build(self, graph, class_name):
        from craftgraph.qt_nodes import IDENTIFIER

        node = graph.create_node(f"{IDENTIFIER}.{class_name}")
        node._maybe_build_widgets()
        names = list(node._cg_field_states.keys())
        # ingredients (the only INGREDIENT_LIST field) must never appear in the grid.
        assert "ingredients" not in names
        assert len(names) > 0

    def test_get_property_still_works(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER
        from craftgraph.models import ModifiedRecipe

        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        node.model_ref = ModifiedRecipe(item_id="Titanium", amount_crafted=5)
        node.populate_from_model()
        node._maybe_build_widgets()
        assert node.get_property("item_id") == "Titanium"
        assert int(node.get_property("amount_crafted")) == 5

    def test_subclass_added_recipe_uses_painted_fields(self, graph):
        """After broadening: AddedRecipeNode (subclass) also uses the painted path."""
        from craftgraph.qt_nodes import IDENTIFIER, PaintedFieldsNodeItem

        node = graph.create_node(f"{IDENTIFIER}.AddedRecipeNode")
        node._maybe_build_widgets()
        assert isinstance(node.view, PaintedFieldsNodeItem)
        assert node.get_widget("item_id") is None


class TestIngredientRequiredMapping:
    def _wire(self, graph, n_ingredients):
        from craftgraph.models import Ingredient, ModifiedRecipe

        consumer = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Consumer")
        consumer.model_ref = ModifiedRecipe(
            item_id="Consumer",
            ingredients=[Ingredient(f"Mat{i}", i + 1) for i in range(n_ingredients)],
        )
        src = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Src")
        out = src.get_output("output")
        for i in range(n_ingredients):
            out.connect_to(consumer.get_input(f"ingredient_{i}"))
        return consumer, src

    def test_required_values_keyed_by_connected_port(self, graph):
        consumer, _src = self._wire(graph, 2)
        assert consumer.ingredient_required_values() == {
            "ingredient_0": "1",
            "ingredient_1": "2",
        }

    def test_index_for_port(self, graph):
        consumer, _src = self._wire(graph, 3)
        assert consumer.ingredient_index_for_port("ingredient_0") == 0
        assert consumer.ingredient_index_for_port("ingredient_2") == 2

    def test_unconnected_port_has_no_value(self, graph):
        consumer, _src = self._wire(graph, 1)
        # ingredient_1 is the spawned empty placeholder, not connected.
        assert "ingredient_1" not in consumer.ingredient_required_values()

    def test_middle_disconnect_keeps_mapping_aligned(self, graph):
        consumer, src = self._wire(graph, 3)
        # Simulate RemoveIngredientCommand on the middle ingredient: drop the
        # connection and the model entry together.
        consumer.get_input("ingredient_1").disconnect_from(src.get_output("output"))
        consumer.model_ref.ingredients.pop(1)
        assert consumer.ingredient_required_values() == {
            "ingredient_0": "1",
            "ingredient_2": "3",
        }
        assert consumer.ingredient_index_for_port("ingredient_2") == 1

    def test_no_model_returns_empty(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="X")
        assert node.ingredient_required_values() == {}
        assert node.ingredient_index_for_port("ingredient_0") is None


class TestSetIngredientRequired:
    def _wire(self, graph):
        from craftgraph.commands import EditHistory
        from craftgraph.models import Ingredient, ModifiedRecipe

        consumer = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Consumer")
        consumer.model_ref = ModifiedRecipe(
            item_id="Consumer",
            ingredients=[Ingredient("Titanium", 3)],
        )
        consumer.set_edit_history(EditHistory())
        src = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="Src")
        src.get_output("output").connect_to(consumer.get_input("ingredient_0"))
        return consumer

    def test_updates_model_required(self, graph):
        consumer = self._wire(graph)
        assert consumer.set_ingredient_required("ingredient_0", "7") is True
        assert consumer.model_ref.ingredients[0].required == 7
        assert consumer.model_ref.ingredients[0].item_id == "Titanium"

    def test_clamps_above_max(self, graph):
        consumer = self._wire(graph)
        consumer.set_ingredient_required("ingredient_0", "999")
        assert consumer.model_ref.ingredients[0].required == 25

    def test_clamps_below_min(self, graph):
        consumer = self._wire(graph)
        consumer.set_ingredient_required("ingredient_0", "0")
        assert consumer.model_ref.ingredients[0].required == 1

    def test_empty_value_is_noop(self, graph):
        consumer = self._wire(graph)
        assert consumer.set_ingredient_required("ingredient_0", "  ") is False
        assert consumer.model_ref.ingredients[0].required == 3

    def test_non_integer_is_noop(self, graph):
        consumer = self._wire(graph)
        assert consumer.set_ingredient_required("ingredient_0", "abc") is False
        assert consumer.model_ref.ingredients[0].required == 3

    def test_unchanged_value_is_noop(self, graph):
        consumer = self._wire(graph)
        assert consumer.set_ingredient_required("ingredient_0", "3") is False

    def test_undo_restores_previous(self, graph):
        consumer = self._wire(graph)
        consumer.set_ingredient_required("ingredient_0", "8")
        consumer._edit_history.undo()
        assert consumer.model_ref.ingredients[0].required == 3
