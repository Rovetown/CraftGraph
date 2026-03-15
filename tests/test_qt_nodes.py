"""Tests for the NodeGraphQt node subclass hierarchy (Step M2).

These tests require the ``qt`` optional dependency group (PySide6 + NodeGraphQt).
They are skipped automatically when those packages are not installed.

Run:  uv run --extra qt pytest tests/test_qt_nodes.py -v
"""

from __future__ import annotations

import sys
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
        """Every non-INGREDIENT_LIST field should have a widget."""
        from craftgraph.pin_registry import PinType
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        for fp in node.FIELD_REGISTRY:
            if fp.pin_type == PinType.INGREDIENT_LIST:
                continue
            assert node.get_widget(fp.name) is not None, f"Missing widget: {fp.name}"

    def test_output_pins_exist(self, graph):
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        for op in node.OUTPUT_PINS:
            assert node.get_output(op.name) is not None, f"Missing output: {op.name}"

    def test_registry_has_all_model_fields(self, graph):
        """FIELD_REGISTRY covers all ModifiedRecipe model fields."""
        expected = {
            "item_id", "amount_crafted", "ingredients", "linked_item_ids",
            "unlocks", "unlocked_by", "force_unlock_at_start",
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
        """Fields that were missing before Phase A should now exist."""
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        assert node.get_widget("linked_item_ids") is not None
        assert node.get_widget("unlocks") is not None
        assert node.get_widget("unlocked_by") is not None
        assert node.get_widget("force_unlock_at_start") is not None

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
        assert node.get_widget("path") is not None
        assert node.get_widget("pda_group") is not None
        assert node.get_widget("pda_category") is not None

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
        assert node.get_widget("path") is not None
        assert node.get_widget("pda_group") is not None

    def test_own_fields_present(self, graph):
        node = graph.create_node("com.craftgraph.AliasRecipeNode", name="Al1")
        assert node.get_widget("display_name") is not None
        assert node.get_widget("tooltip") is not None
        assert node.get_widget("functional_id") is not None
        assert node.get_widget("sprite_item_id") is not None

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
        assert node.get_widget("display_name") is not None
        assert node.get_widget("tooltip") is not None

    def test_all_food_stat_fields(self, graph):
        node = graph.create_node("com.craftgraph.CustomFoodNode", name="F1")
        for field_name in ("food_value", "water_value", "oxygen_value",
                           "health_value", "decay_rate_mod"):
            assert node.get_widget(field_name) is not None, f"Missing: {field_name}"

    def test_food_type_and_drink_sound(self, graph):
        node = graph.create_node("com.craftgraph.CustomFoodNode", name="F1")
        assert node.get_widget("food_type") is not None
        assert node.get_widget("use_drink_sound") is not None

    def test_populate_food_stats(self, graph):
        from craftgraph.models import CustomFood
        food = CustomFood(
            item_id="SpicyTuna", food_value=30, water_value=-5,
            oxygen_value=10, health_value=5, decay_rate_mod=1.5,
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
        assert node.get_widget("item_id") is not None
        assert node.get_widget("amount_crafted") is not None

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

    def test_path_widget(self, graph):
        node = graph.create_node("com.craftgraph.AddedRecipeNode", name="A1")
        assert node.get_widget("path") is not None

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

    def test_display_name_and_tooltip_widgets(self, graph):
        node = graph.create_node("com.craftgraph.AliasRecipeNode", name="Al1")
        assert node.get_widget("display_name") is not None
        assert node.get_widget("tooltip") is not None

    def test_inherits_path_widget(self, graph):
        node = graph.create_node("com.craftgraph.AliasRecipeNode", name="Al1")
        assert node.get_widget("path") is not None

    def test_node_color(self, graph):
        from craftgraph.qt_nodes import NODE_COLOR_ALIAS_RECIPE
        node = graph.create_node("com.craftgraph.AliasRecipeNode", name="Al1")
        assert node.color() == NODE_COLOR_ALIAS_RECIPE


class TestCustomFoodNode:

    def test_food_stat_widgets(self, graph):
        node = graph.create_node("com.craftgraph.CustomFoodNode", name="F1")
        assert node.get_widget("food_value") is not None
        assert node.get_widget("water_value") is not None

    def test_inherits_alias_widgets(self, graph):
        node = graph.create_node("com.craftgraph.CustomFoodNode", name="F1")
        assert node.get_widget("display_name") is not None
        assert node.get_widget("tooltip") is not None
        assert node.get_widget("path") is not None

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
        assert node.get_output("children") is not None
        # Fabricator has only the sprite_in input (from base class)
        assert node.get_input("sprite_in") is not None
        assert len(node.input_ports()) == 1

    def test_widgets(self, graph):
        node = graph.create_node("com.craftgraph.FabricatorNode", name="Fab1")
        assert node.get_widget("item_id") is not None
        assert node.get_widget("display_name") is not None
        assert node.get_widget("model") is not None

    def test_node_color(self, graph):
        from craftgraph.qt_nodes import NODE_COLOR_FABRICATOR
        node = graph.create_node("com.craftgraph.FabricatorNode", name="Fab1")
        assert node.color() == NODE_COLOR_FABRICATOR


class TestCraftingTabNode:

    def test_ports(self, graph):
        node = graph.create_node("com.craftgraph.CraftingTabNode", name="Tab1")
        assert node.get_input("parent") is not None
        assert node.get_output("children") is not None

    def test_widgets(self, graph):
        node = graph.create_node("com.craftgraph.CraftingTabNode", name="Tab1")
        assert node.get_widget("tab_id") is not None
        assert node.get_widget("display_name") is not None

    def test_node_color(self, graph):
        from craftgraph.qt_nodes import NODE_COLOR_CRAFTING_TAB
        node = graph.create_node("com.craftgraph.CraftingTabNode", name="Tab1")
        assert node.color() == NODE_COLOR_CRAFTING_TAB


class TestMovedRecipeNode:

    def test_ports(self, graph):
        node = graph.create_node("com.craftgraph.MovedRecipeNode", name="M1")
        # Only sprite_in from base class
        assert node.get_input("sprite_in") is not None
        assert len(node.input_ports()) == 1
        assert node.output_ports() == []

    def test_widgets(self, graph):
        node = graph.create_node("com.craftgraph.MovedRecipeNode", name="M1")
        assert node.get_widget("item_id") is not None
        assert node.get_widget("old_path") is not None
        assert node.get_widget("new_path") is not None
        assert node.get_widget("copied") is not None
        assert node.get_widget("hidden") is not None

    def test_node_color(self, graph):
        from craftgraph.qt_nodes import NODE_COLOR_MOVED_RECIPE
        node = graph.create_node("com.craftgraph.MovedRecipeNode", name="M1")
        assert node.color() == NODE_COLOR_MOVED_RECIPE


class TestCustomBioFuelNode:

    def test_ports(self, graph):
        node = graph.create_node("com.craftgraph.CustomBioFuelNode", name="BF1")
        assert node.get_input("sprite_in") is not None
        assert len(node.input_ports()) == 1
        assert node.output_ports() == []

    def test_widgets(self, graph):
        node = graph.create_node("com.craftgraph.CustomBioFuelNode", name="BF1")
        assert node.get_widget("item_id") is not None
        assert node.get_widget("energy") is not None

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
        assert node.get_input("sprite_in") is not None
        assert len(node.input_ports()) == 1
        assert node.output_ports() == []

    def test_widgets(self, graph):
        node = graph.create_node("com.craftgraph.CustomFragmentCountNode", name="FC1")
        assert node.get_widget("item_id") is not None
        assert node.get_widget("fragments_to_scan") is not None

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
            "ModifiedRecipe", "AddedRecipe", "AliasRecipe",
            "CustomFood", "Fabricator", "CraftingTab", "CustomSize",
            "MovedRecipe", "CustomBioFuel", "CustomFragmentCount",
            "OrphanIngredient", "Sprite",
        }
        assert {k.value for k in NodeKind} == expected


# ---------------------------------------------------------------------------
# Orphan ingredient node (Step M7.8)
# ---------------------------------------------------------------------------

class TestOrphanIngredientNode:

    def test_create_orphan_ingredient(self, graph):
        """OrphanIngredientNode can be created and has expected ports."""
        node = graph.create_node(
            "com.craftgraph.OrphanIngredientNode", name="OrphanTest",
        )
        assert node is not None
        assert node.get_output("output") is not None

    def test_orphan_has_grey_color(self, graph):
        """OrphanIngredientNode uses the muted grey color."""
        node = graph.create_node(
            "com.craftgraph.OrphanIngredientNode", name="Grey",
        )
        color = node.color()
        assert color[:3] == (90, 90, 90)

    def test_orphan_has_item_id_widget(self, graph):
        """OrphanIngredientNode exposes an item_id text input."""
        node = graph.create_node(
            "com.craftgraph.OrphanIngredientNode", name="Widget",
        )
        node.set_property("item_id", "Gold")
        assert node.get_property("item_id") == "Gold"

    def test_orphan_has_no_model_ref(self, graph):
        """OrphanIngredientNode starts with model_ref = None."""
        node = graph.create_node(
            "com.craftgraph.OrphanIngredientNode", name="NoModel",
        )
        assert node.model_ref is None

    def test_orphan_output_connects_to_recipe_ingredient(self, graph):
        """OrphanIngredientNode output can connect to a recipe ingredient port."""
        orphan = graph.create_node(
            "com.craftgraph.OrphanIngredientNode", name="Orphan",
        )
        recipe = graph.create_node(
            "com.craftgraph.ModifiedRecipeNode", name="Recipe",
        )
        out_port = orphan.get_output("output")
        in_port = recipe.get_input("ingredient_0")
        out_port.connect_to(in_port)
        assert in_port.connected_ports()


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

    def test_sprite_connects_to_recipe_sprite_in(self, graph):
        """SpriteNode sprite_out can connect to a recipe's sprite_in port."""
        sprite = graph.create_node("com.craftgraph.SpriteNode", name="Sprite1")
        recipe = graph.create_node(
            "com.craftgraph.ModifiedRecipeNode", name="Recipe",
        )
        out_port = sprite.get_output("sprite_out")
        in_port = recipe.get_input("sprite_in")
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
                f"com.craftgraph.{node_type}", name=f"T_{node_type}",
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
        """Fabricator -> Recipe hierarchy connection should succeed."""
        fab = graph.create_node("com.craftgraph.FabricatorNode", name="Fab")
        recipe = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        fab.get_output("children").connect_to(recipe.get_input("hierarchy"))
        assert len(recipe.get_input("hierarchy").connected_ports()) == 1

    def test_tab_to_recipe_hierarchy_connection(self, graph):
        """Tab -> Recipe hierarchy connection should succeed."""
        tab = graph.create_node("com.craftgraph.CraftingTabNode", name="T1")
        recipe = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        tab.get_output("children").connect_to(recipe.get_input("hierarchy"))
        assert len(recipe.get_input("hierarchy").connected_ports()) == 1

    def test_fab_to_tab_hierarchy_connection(self, graph):
        """Fabricator -> Tab parent connection should succeed."""
        fab = graph.create_node("com.craftgraph.FabricatorNode", name="Fab")
        tab = graph.create_node("com.craftgraph.CraftingTabNode", name="T1")
        fab.get_output("children").connect_to(tab.get_input("parent"))
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
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        node.set_property("item_id", "Titanium")
        assert node.get_widget("item_id").get_value() == "Titanium"

    def test_recipe_amount_set_get(self, graph):
        """NodeSpinBox.get_value() returns a string (NodeGraphQt stores all values as str)."""
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode", name="R1")
        node.set_property("amount_crafted", 5)
        assert node.get_widget("amount_crafted").get_value() == "5"

    def test_fab_model_set_get(self, graph):
        node = graph.create_node("com.craftgraph.FabricatorNode", name="Fab1")
        node.set_property("model", "Workbench")
        assert node.get_widget("model").get_value() == "Workbench"

    def test_tab_id_set_get(self, graph):
        node = graph.create_node("com.craftgraph.CraftingTabNode", name="T1")
        node.set_property("tab_id", "Weapons")
        assert node.get_widget("tab_id").get_value() == "Weapons"


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
