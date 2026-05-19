"""Tests for the Model-to-UI sync layer (Step M4).

Tests for SyncGuard do not require Qt dependencies.
Tests that need NodeGraphQt are grouped separately and skipped
when Qt deps are missing.

Run (guard tests only):  uv run pytest tests/test_sync.py -v
Run (all, with Qt):      uv run --extra qt pytest tests/test_sync.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from craftgraph.sync import SyncGuard

# ---------------------------------------------------------------------------
# SyncGuard tests (no Qt needed)
# ---------------------------------------------------------------------------


class TestSyncGuard:
    def test_initially_inactive(self):
        guard = SyncGuard()
        assert not guard.active

    def test_active_inside_context(self):
        guard = SyncGuard()
        with guard():
            assert guard.active

    def test_inactive_after_context(self):
        guard = SyncGuard()
        with guard():
            pass
        assert not guard.active

    def test_reentrant_nesting(self):
        guard = SyncGuard()
        with guard():
            assert guard.active
            with guard():
                assert guard.active
            assert guard.active
        assert not guard.active

    def test_active_after_exception(self):
        """Guard resets even if the block raises."""
        guard = SyncGuard()
        with pytest.raises(ValueError, match="boom"), guard():
            raise ValueError("boom")
        assert not guard.active

    def test_prevents_recursive_calls(self):
        """Simulate the model<->UI recursion scenario."""
        guard = SyncGuard()
        call_log: list[str] = []

        def on_model_changed() -> None:
            if guard.active:
                return
            with guard():
                call_log.append("model->ui")
                on_ui_changed()

        def on_ui_changed() -> None:
            if guard.active:
                return
            with guard():
                call_log.append("ui->model")
                on_model_changed()

        on_model_changed()
        assert call_log == ["model->ui"]

    def test_reset(self):
        guard = SyncGuard()
        with guard():
            guard.reset()
        assert not guard.active


# ---------------------------------------------------------------------------
# Qt-dependent tests: populate_graph, connect_hierarchy, connect_ingredients
# ---------------------------------------------------------------------------

_qt_available = pytest.importorskip(
    "NodeGraphQt",
    reason="NodeGraphQt not installed (install with: uv sync --extra qt)",
)

from PySide6 import QtWidgets

from craftgraph.commands import EditHistory
from craftgraph.models import (
    AddedRecipe,
    AliasRecipe,
    CraftingTab,
    CustomFabricator,
    CustomFood,
    CustomSize,
    Ingredient,
    ModifiedRecipe,
    MovedRecipe,
    ParsedFile,
)
from craftgraph.qt_nodes import all_node_classes
from craftgraph.sync import (
    _LAYOUT_X_CHILD_OFFSET,
    _LAYOUT_X_FAB,
    _LAYOUT_X_RECIPE,
    _LAYOUT_X_TAB,
    _LAYOUT_Y_GROUP_GAP,
    _LAYOUT_Y_STEP,
    _node_step,
    UIToModelHandler,
    apply_layout,
    compute_hierarchy_layout,
    connect_hierarchy,
    connect_ingredients,
    highlight_cycle_edges,
    place_orphan_nodes,
    populate_graph,
    update_child_count_labels,
    update_node_issue_overlays,
)


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


@pytest.fixture
def graph(qapp):
    """Fresh NodeGraph with all CraftGraph nodes registered."""
    from NodeGraphQt import NodeGraph

    g = NodeGraph()
    g.set_acyclic(False)
    for cls in all_node_classes():
        g.register_node(cls)
    return g


def _make_parsed_file(**kwargs) -> ParsedFile:
    """Helper to create a ParsedFile with defaults."""
    kwargs.setdefault("source_path", Path("test.txt"))
    return ParsedFile(**kwargs)


# ---------------------------------------------------------------------------
# populate_graph tests
# ---------------------------------------------------------------------------


class TestSyncGuardSuspendUndo:
    def test_undo_stack_cleared_after_suspended_block(self, graph):
        """Watcher path mutates without leaving undo entries.

        QUndoStack does not expose pop-without-apply, so the entire stack is
        cleared on exit. This matches NodeGraphQt's deserialize_session
        behavior used by the pre-2.2 full-reload watcher path.
        """
        from craftgraph.qt_nodes import IDENTIFIER

        # User performs an action before the watcher event fires.
        graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        assert graph.undo_stack().count() >= 1

        with SyncGuard(suspend_undo_for=graph):
            graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
            graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")

        assert graph.undo_stack().count() == 0

    def test_no_target_leaves_stack_alone(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER

        graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        baseline = graph.undo_stack().count()

        with SyncGuard():
            pass

        assert graph.undo_stack().count() == baseline

    def test_suspend_undo_recursion_guard_active_inside_block(self, graph):
        guard = SyncGuard(suspend_undo_for=graph)
        with guard:
            assert guard.active
        assert not guard.active


class TestPopulateGraph:
    def test_empty_files_produce_no_nodes(self, graph):
        pf = _make_parsed_file()
        result = populate_graph(graph, [pf])
        assert len(result) == 0
        assert len(graph.all_nodes()) == 0

    def test_modified_recipe_creates_node(self, graph):
        recipe = ModifiedRecipe(item_id="Titanium", amount_crafted=2)
        pf = _make_parsed_file(modified_recipes=[recipe])
        result = populate_graph(graph, [pf])

        assert len(result) == 1
        node = result[id(recipe)]
        node._maybe_build_widgets()
        assert node.name() == "Titanium (x2)"
        assert node.model_ref is recipe
        # Painted-fields path: ModifiedRecipeNode stores values as properties only.
        assert int(node.get_property("amount_crafted")) == 2

    def test_added_recipe_has_path(self, graph):
        recipe = AddedRecipe(item_id="Alloy", path="Fabricator/Resources")
        pf = _make_parsed_file(added_recipes=[recipe])
        result = populate_graph(graph, [pf])

        node = result[id(recipe)]
        node._maybe_build_widgets()
        # Painted-fields path: AddedRecipeNode stores values as properties only.
        assert node.get_property("path") == "Fabricator/Resources"
        assert node.get_widget("path") is None

    def test_alias_recipe_has_display_fields(self, graph):
        recipe = AliasRecipe(
            item_id="SuperItem",
            display_name="Super Item",
            tooltip="A super item",
        )
        pf = _make_parsed_file(alias_recipes=[recipe])
        result = populate_graph(graph, [pf])

        node = result[id(recipe)]
        node._maybe_build_widgets()
        # Painted-fields path: AliasRecipeNode stores values as properties only.
        assert node.get_property("display_name") == "Super Item"
        assert node.get_property("tooltip") == "A super item"
        assert node.get_widget("display_name") is None

    def test_custom_food_has_stat_fields(self, graph):
        recipe = CustomFood(item_id="Snack", food_value=50, water_value=30)
        pf = _make_parsed_file(custom_foods=[recipe])
        result = populate_graph(graph, [pf])

        node = result[id(recipe)]
        node._maybe_build_widgets()
        # Painted-fields path: CustomFoodNode stores values as properties only.
        # INT fields return the raw int (convert_to_display falls through to case _:).
        assert node.get_property("food_value") == 50
        assert node.get_property("water_value") == 30
        assert node.get_widget("food_value") is None

    def test_fabricator_creates_nested_nodes(self, graph):
        tab = CraftingTab(tab_id="Potions", display_name="Potions")
        added = AddedRecipe(item_id="HealthPotion", path="Potions")
        fab = CustomFabricator(
            item_id="AlchemyStation",
            display_name="Alchemy Station",
            model="Workbench",
            tabs=[tab],
            added_recipes=[added],
        )
        pf = _make_parsed_file(custom_fabricators=[fab])
        result = populate_graph(graph, [pf])

        assert len(result) == 3
        assert id(fab) in result
        assert id(tab) in result
        assert id(added) in result

    def test_fabricator_node_properties(self, graph):
        fab = CustomFabricator(
            item_id="MyFab",
            display_name="My Fab",
            model="Workbench",
        )
        pf = _make_parsed_file(custom_fabricators=[fab])
        result = populate_graph(graph, [pf])

        node = result[id(fab)]
        node._maybe_build_widgets()
        assert node.get_property("item_id") == "MyFab"
        assert node.get_property("display_name") == "My Fab"

    def test_top_level_tab(self, graph):
        tab = CraftingTab(tab_id="Resources", display_name="Resources")
        pf = _make_parsed_file(crafting_tabs=[tab])
        result = populate_graph(graph, [pf])

        assert len(result) == 1
        node = result[id(tab)]
        node._maybe_build_widgets()
        assert node.get_property("tab_id") == "Resources"

    def test_multiple_files(self, graph):
        r1 = ModifiedRecipe(item_id="A")
        r2 = ModifiedRecipe(item_id="B")
        pf1 = _make_parsed_file(modified_recipes=[r1])
        pf2 = _make_parsed_file(modified_recipes=[r2])
        result = populate_graph(graph, [pf1, pf2])

        assert len(result) == 2
        assert id(r1) in result
        assert id(r2) in result


# ---------------------------------------------------------------------------
# populate_graph with edit_history tests
# ---------------------------------------------------------------------------


class TestPopulateGraphWithEditHistory:
    def test_edit_history_injected_into_nodes(self, graph, qapp):
        recipe = ModifiedRecipe(item_id="Titanium", amount_crafted=1)
        pf = _make_parsed_file(modified_recipes=[recipe])
        history = EditHistory()
        model_to_node = populate_graph(graph, [pf], edit_history=history)
        node = model_to_node[id(recipe)]
        assert node._edit_history is history

    def test_populate_sets_widget_values(self, graph, qapp):
        recipe = ModifiedRecipe(
            item_id="Gold",
            amount_crafted=5,
            linked_item_ids=["Silver", "Lead"],
        )
        pf = _make_parsed_file(modified_recipes=[recipe])
        model_to_node = populate_graph(graph, [pf])
        node = model_to_node[id(recipe)]
        assert node.get_property("item_id") == "Gold"
        assert int(node.get_property("amount_crafted")) == 5
        assert node.get_property("linked_item_ids") == "Silver, Lead"


# ---------------------------------------------------------------------------
# connect_hierarchy tests
# ---------------------------------------------------------------------------


class TestConnectHierarchy:
    def test_fab_to_tab_connection(self, graph):
        tab = CraftingTab(tab_id="Potions")
        fab = CustomFabricator(item_id="Fab", tabs=[tab])
        pf = _make_parsed_file(custom_fabricators=[fab])

        m2n = populate_graph(graph, [pf])
        count = connect_hierarchy(graph, [pf], m2n)

        assert count == 1
        tab_node = m2n[id(tab)]
        parent_port = tab_node.get_input("parent")
        assert len(parent_port.connected_ports()) == 1

    def test_fab_to_recipe_connection(self, graph):
        recipe = AddedRecipe(item_id="Potion")
        fab = CustomFabricator(item_id="Fab", added_recipes=[recipe])
        pf = _make_parsed_file(custom_fabricators=[fab])

        m2n = populate_graph(graph, [pf])
        count = connect_hierarchy(graph, [pf], m2n)

        assert count == 1
        recipe_node = m2n[id(recipe)]
        hier_port = recipe_node.get_input("hierarchy")
        assert len(hier_port.connected_ports()) == 1

    def test_fab_with_multiple_children(self, graph):
        tab = CraftingTab(tab_id="Tab1")
        r1 = AddedRecipe(item_id="R1")
        r2 = AliasRecipe(item_id="R2")
        r3 = CustomFood(item_id="R3")
        fab = CustomFabricator(
            item_id="Fab",
            tabs=[tab],
            added_recipes=[r1],
            alias_recipes=[r2],
            custom_foods=[r3],
        )
        pf = _make_parsed_file(custom_fabricators=[fab])

        m2n = populate_graph(graph, [pf])
        count = connect_hierarchy(graph, [pf], m2n)

        assert count == 4  # 1 tab + 3 recipes

    def test_nested_tab_connects_to_parent_tab(self, graph):
        """A child tab with parent_tab_path should connect to its parent tab,
        not directly to the fabricator."""
        parent_tab = CraftingTab(
            tab_id="ComplexCompounds",
            parent_tab_path="Fab",
        )
        child_tab = CraftingTab(
            tab_id="Enzymes",
            parent_tab_path="Fab/ComplexCompounds",
        )
        fab = CustomFabricator(
            item_id="Fab",
            tabs=[parent_tab, child_tab],
        )
        pf = _make_parsed_file(custom_fabricators=[fab])

        m2n = populate_graph(graph, [pf])
        connect_hierarchy(graph, [pf], m2n)

        # parent_tab should be connected to the fabricator's tabs_out port
        parent_tab_node = m2n[id(parent_tab)]
        parent_port = parent_tab_node.get_input("parent")
        fab_node = m2n[id(fab)]
        fab_tabs_out = fab_node.get_output("tabs_out")
        assert fab_tabs_out in parent_port.connected_ports()

        # child_tab should be connected to parent_tab, NOT to the fabricator
        child_tab_node = m2n[id(child_tab)]
        child_parent_port = child_tab_node.get_input("parent")
        connected = child_parent_port.connected_ports()
        assert len(connected) == 1
        # The connected port should be parent_tab's "children" output
        assert connected[0] == parent_tab_node.get_output("children")

    def test_recipe_connects_to_its_tab_via_path(self, graph):
        """A recipe with a path should connect to the tab, not the fabricator."""
        tab = CraftingTab(tab_id="Potions", parent_tab_path="Fab")
        recipe = AddedRecipe(item_id="HealthPotion", path="Fab/Potions")
        fab = CustomFabricator(
            item_id="Fab",
            tabs=[tab],
            added_recipes=[recipe],
        )
        pf = _make_parsed_file(custom_fabricators=[fab])

        m2n = populate_graph(graph, [pf])
        connect_hierarchy(graph, [pf], m2n)

        recipe_node = m2n[id(recipe)]
        hier_port = recipe_node.get_input("hierarchy")
        connected = hier_port.connected_ports()
        assert len(connected) == 1
        # Should connect to tab's children, not fabricator's children
        tab_node = m2n[id(tab)]
        assert connected[0] == tab_node.get_output("children")

    def test_no_connections_without_fabs(self, graph):
        recipe = ModifiedRecipe(item_id="Solo")
        pf = _make_parsed_file(modified_recipes=[recipe])

        m2n = populate_graph(graph, [pf])
        count = connect_hierarchy(graph, [pf], m2n)

        assert count == 0


# ---------------------------------------------------------------------------
# connect_ingredients tests
# ---------------------------------------------------------------------------


class TestConnectIngredients:
    def test_ingredient_connection(self, graph):
        """Recipe A uses ingredient B; B has its own recipe node."""
        recipe_b = ModifiedRecipe(item_id="Titanium")
        recipe_a = ModifiedRecipe(
            item_id="Alloy",
            ingredients=[Ingredient(item_id="Titanium", required=2)],
        )
        pf = _make_parsed_file(modified_recipes=[recipe_b, recipe_a])

        m2n = populate_graph(graph, [pf])
        result = connect_ingredients(graph, [pf], m2n)

        assert result.count == 1
        alloy_node = m2n[id(recipe_a)]
        ing_ports = [p for p in alloy_node.input_ports() if p.name().startswith("ingredient_")]
        connected = [p for p in ing_ports if p.connected_ports()]
        assert len(connected) == 1

    def test_no_connection_for_unknown_ingredient(self, graph):
        """Ingredients without matching recipe nodes get orphan nodes instead."""
        recipe = ModifiedRecipe(
            item_id="Alloy",
            ingredients=[Ingredient(item_id="UnknownMaterial", required=1)],
        )
        pf = _make_parsed_file(modified_recipes=[recipe])

        m2n = populate_graph(graph, [pf])
        result = connect_ingredients(graph, [pf], m2n)

        # Orphan created and connected (count=1), not 0
        assert result.count == 1
        assert "unknownmaterial" in result.orphan_nodes

    def test_case_insensitive_matching(self, graph):
        """Ingredient matching is case-insensitive (CC3 behavior)."""
        recipe_src = ModifiedRecipe(item_id="titanium")
        recipe_use = ModifiedRecipe(
            item_id="Alloy",
            ingredients=[Ingredient(item_id="Titanium", required=1)],
        )
        pf = _make_parsed_file(modified_recipes=[recipe_src, recipe_use])

        m2n = populate_graph(graph, [pf])
        result = connect_ingredients(graph, [pf], m2n)

        assert result.count == 1


    def test_fabricator_ingredient_wired_not_orphaned(self, graph):
        """Fabricator with ingredients should wire them, not create orphans."""
        titanium = ModifiedRecipe(item_id="Titanium")
        fab = CustomFabricator(
            item_id="MyFab",
            ingredients=[Ingredient(item_id="Titanium", required=2)],
        )
        pf = _make_parsed_file(modified_recipes=[titanium], custom_fabricators=[fab])

        m2n = populate_graph(graph, [pf])
        result = connect_ingredients(graph, [pf], m2n)

        # Should be a direct connection, not an orphan
        assert result.count == 1
        assert len(result.orphan_nodes) == 0

        fab_node = m2n[id(fab)]
        ing_ports = [p for p in fab_node.input_ports() if p.name().startswith("ingredient_")]
        connected = [p for p in ing_ports if p.connected_ports()]
        assert len(connected) == 1

    def test_fabricator_unknown_ingredient_gets_orphan(self, graph):
        """Fabricator ingredient with no matching node gets an orphan."""
        fab = CustomFabricator(
            item_id="MyFab",
            ingredients=[Ingredient(item_id="RawGold", required=3)],
        )
        pf = _make_parsed_file(custom_fabricators=[fab])

        m2n = populate_graph(graph, [pf])
        result = connect_ingredients(graph, [pf], m2n)

        assert "rawgold" in result.orphan_nodes
        fab_node = m2n[id(fab)]
        ing_ports = [p for p in fab_node.input_ports() if p.name().startswith("ingredient_")]
        connected = [p for p in ing_ports if p.connected_ports()]
        assert len(connected) == 1


# ---------------------------------------------------------------------------
# Step 11h: OrphanIngredientNode auto-creation tests
# ---------------------------------------------------------------------------


class TestOrphanIngredientCreation:
    """connect_ingredients creates OrphanIngredientNodes for raw materials."""

    def test_raw_material_gets_orphan_node(self, graph):
        """Ingredient with no recipe on canvas gets an OrphanIngredientNode."""
        recipe = ModifiedRecipe(
            item_id="Alloy",
            ingredients=[Ingredient(item_id="Titanium", required=2)],
        )
        pf = _make_parsed_file(modified_recipes=[recipe])

        m2n = populate_graph(graph, [pf])
        result = connect_ingredients(graph, [pf], m2n)

        assert result.orphan_nodes
        assert "titanium" in result.orphan_nodes
        orphan = result.orphan_nodes["titanium"]
        assert orphan.get_property("item_id") == "Titanium"

    def test_orphan_connected_to_consumer(self, graph):
        """The OrphanIngredientNode's output is wired to the recipe's ingredient slot."""
        recipe = ModifiedRecipe(
            item_id="Alloy",
            ingredients=[Ingredient(item_id="Titanium", required=2)],
        )
        pf = _make_parsed_file(modified_recipes=[recipe])

        m2n = populate_graph(graph, [pf])
        result = connect_ingredients(graph, [pf], m2n)

        alloy_node = m2n[id(recipe)]
        ing_ports = [p for p in alloy_node.input_ports() if p.name().startswith("ingredient_")]
        connected = [p for p in ing_ports if p.connected_ports()]
        assert len(connected) == 1
        # The source of the connection is the orphan
        source = connected[0].connected_ports()[0].node()
        assert source is result.orphan_nodes["titanium"]

    def test_one_orphan_per_unique_raw_material(self, graph):
        """Two recipes using the same raw material share one OrphanIngredientNode."""
        recipe_a = ModifiedRecipe(
            item_id="Alloy",
            ingredients=[Ingredient(item_id="Titanium", required=2)],
        )
        recipe_b = ModifiedRecipe(
            item_id="Blade",
            ingredients=[Ingredient(item_id="Titanium", required=1)],
        )
        pf = _make_parsed_file(modified_recipes=[recipe_a, recipe_b])

        m2n = populate_graph(graph, [pf])
        result = connect_ingredients(graph, [pf], m2n)

        assert len(result.orphan_nodes) == 1
        assert "titanium" in result.orphan_nodes

    def test_crafted_ingredient_no_orphan(self, graph):
        """Ingredients that have a recipe node on canvas do NOT get orphans."""
        titanium = ModifiedRecipe(item_id="Titanium")
        alloy = ModifiedRecipe(
            item_id="Alloy",
            ingredients=[Ingredient(item_id="Titanium", required=2)],
        )
        pf = _make_parsed_file(modified_recipes=[titanium, alloy])

        m2n = populate_graph(graph, [pf])
        result = connect_ingredients(graph, [pf], m2n)

        assert len(result.orphan_nodes) == 0
        assert result.count == 1

    def test_mixed_crafted_and_raw(self, graph):
        """Recipe with both crafted and raw ingredients: orphan only for raw."""
        titanium = ModifiedRecipe(item_id="Titanium")
        alloy = ModifiedRecipe(
            item_id="Alloy",
            ingredients=[
                Ingredient(item_id="Titanium", required=2),
                Ingredient(item_id="Gold", required=1),
            ],
        )
        pf = _make_parsed_file(modified_recipes=[titanium, alloy])

        m2n = populate_graph(graph, [pf])
        result = connect_ingredients(graph, [pf], m2n)

        # Titanium is crafted -> direct link, Gold is raw -> orphan
        assert result.count == 2  # one recipe-to-recipe + one orphan-to-recipe
        assert len(result.orphan_nodes) == 1
        assert "gold" in result.orphan_nodes

    def test_count_includes_orphan_connections(self, graph):
        """result.count includes both recipe-to-recipe and orphan-to-recipe links."""
        recipe = ModifiedRecipe(
            item_id="Alloy",
            ingredients=[
                Ingredient(item_id="Copper", required=1),
                Ingredient(item_id="Silver", required=1),
            ],
        )
        pf = _make_parsed_file(modified_recipes=[recipe])

        m2n = populate_graph(graph, [pf])
        result = connect_ingredients(graph, [pf], m2n)

        assert result.count == 2
        assert len(result.orphan_nodes) == 2

    def test_backward_compat_count_attribute(self, graph):
        """Existing callers that check connect_ingredients().count still work."""
        recipe = ModifiedRecipe(item_id="Alloy")
        pf = _make_parsed_file(modified_recipes=[recipe])

        m2n = populate_graph(graph, [pf])
        result = connect_ingredients(graph, [pf], m2n)

        assert result.count == 0
        assert result.orphan_nodes == {}


# ---------------------------------------------------------------------------
# compute_hierarchy_layout / apply_layout tests
# ---------------------------------------------------------------------------


class TestComputeHierarchyLayout:
    def test_empty_file_returns_empty(self, graph):
        pf = _make_parsed_file()
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)
        assert positions == {}

    def test_fabricator_placed_at_fab_column(self, graph):
        fab = CustomFabricator(item_id="Fab")
        pf = _make_parsed_file(custom_fabricators=[fab])
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)

        x, y = positions[id(fab)]
        assert x == _LAYOUT_X_FAB
        assert y == 0.0

    def test_fab_tab_recipe_columns(self, graph):
        """Fab, tab, and recipe get distinct X columns."""
        tab = CraftingTab(tab_id="Potions")
        recipe = AddedRecipe(item_id="Potion", path="Fab/Potions")
        fab = CustomFabricator(
            item_id="Fab",
            tabs=[tab],
            added_recipes=[recipe],
        )
        pf = _make_parsed_file(custom_fabricators=[fab])
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)

        assert positions[id(fab)][0] == _LAYOUT_X_FAB
        assert positions[id(tab)][0] == _LAYOUT_X_TAB
        assert positions[id(recipe)][0] == _LAYOUT_X_RECIPE

    def test_fab_group_y_alignment(self, graph):
        """Fab and tab start at group_start; recipe under tab is one step below."""
        tab = CraftingTab(tab_id="Tab1")
        recipe = AddedRecipe(item_id="R1", path="Fab/Tab1")
        fab = CustomFabricator(
            item_id="Fab",
            tabs=[tab],
            added_recipes=[recipe],
        )
        pf = _make_parsed_file(custom_fabricators=[fab])
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)

        fab_y = positions[id(fab)][1]
        tab_y = positions[id(tab)][1]
        recipe_y = positions[id(recipe)][1]

        # Fab and tab share group_start; recipe placed below its parent tab
        assert fab_y == 0.0
        assert tab_y == 0.0
        assert recipe_y == _node_step(id(tab), m2n)  # below tab, dynamic height

    def test_multiple_tabs_stacked(self, graph):
        """Multiple tabs in a fab are spaced by the first tab's dynamic height."""
        t1 = CraftingTab(tab_id="Tab1")
        t2 = CraftingTab(tab_id="Tab2")
        fab = CustomFabricator(item_id="Fab", tabs=[t1, t2])
        pf = _make_parsed_file(custom_fabricators=[fab])
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)

        assert positions[id(t1)][1] == 0.0
        assert positions[id(t2)][1] == _node_step(id(t1), m2n)

    def test_multiple_recipes_stacked(self, graph):
        """Multiple recipes in a fab are spaced vertically."""
        r1 = AddedRecipe(item_id="R1")
        r2 = AliasRecipe(item_id="R2")
        fab = CustomFabricator(
            item_id="Fab",
            added_recipes=[r1],
            alias_recipes=[r2],
        )
        pf = _make_parsed_file(custom_fabricators=[fab])
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)

        assert positions[id(r1)][1] == 0.0
        assert positions[id(r2)][1] == _node_step(id(r1), m2n)

    def test_two_fab_groups_separated(self, graph):
        """Two fabricator groups are separated by _LAYOUT_Y_GROUP_GAP."""
        fab1 = CustomFabricator(item_id="Fab1")
        fab2 = CustomFabricator(item_id="Fab2")
        pf = _make_parsed_file(custom_fabricators=[fab1, fab2])
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)

        fab1_y = positions[id(fab1)][1]
        fab2_y = positions[id(fab2)][1]
        # fab1 at 0.0, next group at fab1's dynamic height + group gap
        assert fab1_y == 0.0
        assert fab2_y == _node_step(id(fab1), m2n) + _LAYOUT_Y_GROUP_GAP

    def test_top_level_tabs_after_fab_groups(self, graph):
        """Top-level tabs appear after all fabricator groups."""
        fab = CustomFabricator(item_id="Fab")
        tab = CraftingTab(tab_id="TopTab")
        pf = _make_parsed_file(custom_fabricators=[fab], crafting_tabs=[tab])
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)

        tab_y = positions[id(tab)][1]
        fab_y = positions[id(fab)][1]
        assert tab_y > fab_y
        assert positions[id(tab)][0] == _LAYOUT_X_TAB

    def test_top_level_recipes_get_own_column(self, graph):
        """Top-level recipes get column 0 when they are the only type."""
        recipe = ModifiedRecipe(item_id="Solo")
        pf = _make_parsed_file(modified_recipes=[recipe])
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)

        # Only non-fab type present -> column 0 at _LAYOUT_X_TAB
        assert positions[id(recipe)][0] == _LAYOUT_X_TAB

    def test_standalone_entries_get_own_column(self, graph):
        """Custom sizes get column 0 when they are the only type."""
        size = CustomSize(item_id="BigItem", width=3, height=3)
        pf = _make_parsed_file(custom_sizes=[size])
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)

        # Only non-fab type present -> column 0 at _LAYOUT_X_TAB
        assert positions[id(size)][0] == _LAYOUT_X_TAB

    def test_different_types_get_separate_columns(self, graph):
        """Modified recipes and custom sizes sit in distinct columns at same Y."""
        recipe = ModifiedRecipe(item_id="Solo")
        size = CustomSize(item_id="BigItem", width=2, height=2)
        pf = _make_parsed_file(modified_recipes=[recipe], custom_sizes=[size])
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)

        recipe_x, recipe_y = positions[id(recipe)]
        size_x, size_y = positions[id(size)]
        # Both at the same Y (same section start)
        assert recipe_y == size_y
        # Modified recipes come before custom sizes in processing order
        assert recipe_x < size_x
        # Columns are one _LAYOUT_X_CHILD_OFFSET apart
        assert size_x == recipe_x + _LAYOUT_X_CHILD_OFFSET

    def test_all_model_objects_get_positions(self, graph):
        """Every model object in model_to_node gets a position entry."""
        tab = CraftingTab(tab_id="Tab1")
        recipe = AddedRecipe(item_id="R1")
        fab = CustomFabricator(
            item_id="Fab",
            tabs=[tab],
            added_recipes=[recipe],
        )
        top_recipe = ModifiedRecipe(item_id="Solo")
        moved = MovedRecipe(item_id="Moved", old_path="A", new_path="B")
        pf = _make_parsed_file(
            custom_fabricators=[fab],
            modified_recipes=[top_recipe],
            moved_recipes=[moved],
        )
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)

        # All 5 model objects should have positions
        assert id(fab) in positions
        assert id(tab) in positions
        assert id(recipe) in positions
        assert id(top_recipe) in positions
        assert id(moved) in positions

    def test_child_tab_right_of_parent(self, graph):
        """A child tab is positioned to the right (higher X) of its parent."""
        root_tab = CraftingTab(tab_id="Root")
        child_tab = CraftingTab(tab_id="Child", parent_tab_path="Fab/Root")
        recipe = AddedRecipe(item_id="R1", path="Fab/Root/Child")
        fab = CustomFabricator(
            item_id="Fab",
            tabs=[root_tab, child_tab],
            added_recipes=[recipe],
        )
        pf = _make_parsed_file(custom_fabricators=[fab])
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)

        root_x = positions[id(root_tab)][0]
        child_x = positions[id(child_tab)][0]
        recipe_x = positions[id(recipe)][0]

        # Child tab is one step right of root tab
        assert child_x > root_x
        # Recipe is one step right of child tab
        assert recipe_x > child_x

    def test_recipe_below_its_parent_tab(self, graph):
        """Recipes are placed below their parent tab, not at the same Y."""
        tab = CraftingTab(tab_id="Potions")
        r1 = AddedRecipe(item_id="PotionA", path="Fab/Potions")
        r2 = AddedRecipe(item_id="PotionB", path="Fab/Potions")
        fab = CustomFabricator(
            item_id="Fab",
            tabs=[tab],
            added_recipes=[r1, r2],
        )
        pf = _make_parsed_file(custom_fabricators=[fab])
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)

        tab_y = positions[id(tab)][1]
        r1_y = positions[id(r1)][1]
        r2_y = positions[id(r2)][1]

        # Both recipes are below the tab (DFS order)
        assert r1_y > tab_y
        assert r2_y > r1_y


class TestApplyLayout:
    def test_sets_node_positions(self, graph):
        """apply_layout calls set_pos on each node."""
        recipe = ModifiedRecipe(item_id="Test")
        pf = _make_parsed_file(modified_recipes=[recipe])
        m2n = populate_graph(graph, [pf])
        positions = {id(recipe): (100.0, 200.0)}

        apply_layout(positions, m2n)

        node = m2n[id(recipe)]
        x, y = node.pos()
        assert x == 100.0
        assert y == 200.0

    def test_skips_missing_nodes(self, graph):
        """Positions for unknown model IDs are silently skipped."""
        pf = _make_parsed_file()
        m2n = populate_graph(graph, [pf])
        positions = {9999: (100.0, 200.0)}

        # Should not raise
        apply_layout(positions, m2n)

    def test_full_layout_pipeline(self, graph):
        """compute_hierarchy_layout + apply_layout sets correct positions."""
        tab = CraftingTab(tab_id="Potions")
        recipe = AddedRecipe(item_id="Potion")
        fab = CustomFabricator(
            item_id="Fab",
            tabs=[tab],
            added_recipes=[recipe],
        )
        pf = _make_parsed_file(custom_fabricators=[fab])
        m2n = populate_graph(graph, [pf])
        positions = compute_hierarchy_layout([pf], m2n)
        apply_layout(positions, m2n)

        fab_node = m2n[id(fab)]
        tab_node = m2n[id(tab)]
        recipe_node = m2n[id(recipe)]

        assert fab_node.pos()[0] == _LAYOUT_X_FAB
        assert tab_node.pos()[0] == _LAYOUT_X_TAB
        assert recipe_node.pos()[0] == _LAYOUT_X_RECIPE


# ---------------------------------------------------------------------------
# place_orphan_nodes tests
# ---------------------------------------------------------------------------


class TestPlaceOrphanNodes:
    """Orphan ingredient nodes should be placed left of their consumers."""

    def test_orphan_placed_left_of_consumer(self, graph):
        """Orphan node X is one offset left of its consumer's X."""
        recipe = ModifiedRecipe(
            item_id="Knife",
            ingredients=[Ingredient(item_id="Titanium", required=2)],
        )
        pf = _make_parsed_file(modified_recipes=[recipe])

        m2n = populate_graph(graph, [pf])
        result = connect_ingredients(graph, [pf], m2n)

        # Place the recipe node at a known position first
        recipe_node = m2n[id(recipe)]
        recipe_node.set_pos(400.0, 100.0)

        place_orphan_nodes(graph)

        orphan = result.orphan_nodes["titanium"]
        ox, oy = orphan.pos()
        assert ox < 400.0  # left of consumer
        assert oy == 100.0  # same Y as single consumer

    def test_orphan_y_is_centroid_of_consumers(self, graph):
        """Orphan Y is the mean of all connected consumer Y positions."""
        r1 = ModifiedRecipe(
            item_id="Knife",
            ingredients=[Ingredient(item_id="Titanium", required=1)],
        )
        r2 = ModifiedRecipe(
            item_id="Sword",
            ingredients=[Ingredient(item_id="Titanium", required=2)],
        )
        pf = _make_parsed_file(modified_recipes=[r1, r2])

        m2n = populate_graph(graph, [pf])
        result = connect_ingredients(graph, [pf], m2n)

        m2n[id(r1)].set_pos(400.0, 0.0)
        m2n[id(r2)].set_pos(400.0, 200.0)

        place_orphan_nodes(graph)

        orphan = result.orphan_nodes["titanium"]
        _, oy = orphan.pos()
        assert oy == 100.0  # mean of 0.0 and 200.0

    def test_orphan_without_connections_stays_put(self, graph):
        """Orphan with no connections keeps its current position."""
        from craftgraph.qt_nodes import IDENTIFIER

        orphan = graph.create_node(
            f"{IDENTIFIER}.OrphanIngredientNode", name="Ghost"
        )
        orphan.set_pos(50.0, 50.0)

        place_orphan_nodes(graph)

        ox, oy = orphan.pos()
        assert ox == 50.0
        assert oy == 50.0


# ---------------------------------------------------------------------------
# UIToModelHandler tests
# ---------------------------------------------------------------------------


@pytest.fixture
def handler_env(graph):
    """Set up a graph with handler, guard, history, and one recipe node."""
    recipe = ModifiedRecipe(item_id="Titanium", amount_crafted=1)
    pf = _make_parsed_file(modified_recipes=[recipe])
    guard = SyncGuard()
    history = EditHistory()

    with guard():
        m2n = populate_graph(graph, [pf], edit_history=history)

    handler = UIToModelHandler(
        graph=graph,
        history=history,
        guard=guard,
        parsed_files=[pf],
    )
    node = m2n[id(recipe)]
    return {
        "graph": graph,
        "handler": handler,
        "history": history,
        "guard": guard,
        "recipe": recipe,
        "node": node,
        "pf": pf,
        "m2n": m2n,
    }


class TestUIToModelPropertyChanged:
    def test_string_property_updates_model(self, handler_env):
        """Changing item_id widget updates the model's item_id."""
        node = handler_env["node"]
        recipe = handler_env["recipe"]

        node.set_property("item_id", "Gold")

        assert recipe.item_id == "Gold"

    def test_int_property_updates_model(self, handler_env):
        """Spinbox int values propagate to the model field."""
        node = handler_env["node"]
        recipe = handler_env["recipe"]

        # NodeGraphQt spinbox requires native int for set_property
        node.set_property("amount_crafted", 5)

        assert recipe.amount_crafted == 5

    def test_history_tracks_changes(self, handler_env):
        """Each property change creates an undo-able command."""
        node = handler_env["node"]
        history = handler_env["history"]

        assert not history.can_undo

        node.set_property("item_id", "Silver")

        assert history.can_undo
        assert history.is_dirty

    def test_undo_restores_old_value(self, handler_env):
        """Undoing a property change restores the previous model value."""
        node = handler_env["node"]
        recipe = handler_env["recipe"]
        history = handler_env["history"]

        assert recipe.item_id == "Titanium"
        node.set_property("item_id", "Gold")
        assert recipe.item_id == "Gold"

        history.undo()
        assert recipe.item_id == "Titanium"

    def test_guard_blocks_during_sync(self, handler_env):
        """Property changes while guard is active do not create commands."""
        node = handler_env["node"]
        recipe = handler_env["recipe"]
        guard = handler_env["guard"]
        history = handler_env["history"]

        with guard():
            node.set_property("item_id", "Blocked")

        # Model not updated (guard was active)
        assert recipe.item_id == "Titanium"
        assert not history.can_undo

    def test_unknown_property_ignored(self, handler_env):
        """NodeGraphQt internal properties don't create commands."""
        history = handler_env["history"]
        node = handler_env["node"]

        # "name" is a NodeGraphQt internal property, not in FIELD_REGISTRY
        node.set_property("name", "NewName")

        assert not history.can_undo

    def test_same_value_skipped(self, handler_env):
        """Setting a property to its current value creates no command."""
        node = handler_env["node"]
        history = handler_env["history"]

        node.set_property("item_id", "Titanium")

        assert not history.can_undo

    def test_disconnect_stops_handling(self, handler_env):
        """After disconnect(), property changes no longer create commands."""
        node = handler_env["node"]
        recipe = handler_env["recipe"]
        handler = handler_env["handler"]
        history = handler_env["history"]

        handler.disconnect()
        node.set_property("item_id", "AfterDisconnect")

        # Model not updated (handler disconnected)
        assert recipe.item_id == "Titanium"
        assert not history.can_undo


class TestUIToModelNonRecipeProperty:
    def test_tab_property_updates_model(self, graph):
        """Property changes on CraftingTabNode update the tab model."""
        tab = CraftingTab(tab_id="Potions", display_name="Potions")
        pf = _make_parsed_file(crafting_tabs=[tab])
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf], edit_history=history)

        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
        )
        tab_node = m2n[id(tab)]

        tab_node.set_property("display_name", "Elixirs")

        assert tab.display_name == "Elixirs"
        assert history.can_undo
        handler.disconnect()

    def test_fab_property_updates_model(self, graph):
        """Property changes on FabricatorNode update the fab model."""
        fab = CustomFabricator(item_id="MyFab", display_name="My Fab")
        pf = _make_parsed_file(custom_fabricators=[fab])
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf], edit_history=history)

        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
        )
        fab_node = m2n[id(fab)]

        fab_node.set_property("display_name", "Super Fab")

        assert fab.display_name == "Super Fab"
        handler.disconnect()


class TestUIToModelIngredientPorts:
    def test_connect_adds_ingredient(self, graph):
        """Connecting output -> ingredient port adds to model ingredients."""
        source = ModifiedRecipe(item_id="Titanium")
        consumer = ModifiedRecipe(item_id="Alloy")
        pf = _make_parsed_file(modified_recipes=[source, consumer])
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])

        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
        )

        source_node = m2n[id(source)]
        consumer_node = m2n[id(consumer)]

        source_out = source_node.get_output("output")
        ing_in = consumer_node.get_input("ingredient_0")
        source_out.connect_to(ing_in)

        assert len(consumer.ingredients) == 1
        assert consumer.ingredients[0].item_id == "Titanium"
        assert consumer.ingredients[0].required == 1
        assert history.can_undo
        handler.disconnect()

    def test_disconnect_removes_ingredient(self, graph):
        """Disconnecting an ingredient port removes it from the model."""
        source = ModifiedRecipe(item_id="Gold")
        consumer = ModifiedRecipe(
            item_id="Ring",
            ingredients=[Ingredient(item_id="Gold", required=3)],
        )
        pf = _make_parsed_file(modified_recipes=[source, consumer])
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])
            # Wire the connection (under guard, so handler doesn't fire)
            source_out = m2n[id(source)].get_output("output")
            ing_in = m2n[id(consumer)].get_input("ingredient_0")
            source_out.connect_to(ing_in)

        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
        )

        # Now disconnect (handler is active)
        source_out = m2n[id(source)].get_output("output")
        ing_in = m2n[id(consumer)].get_input("ingredient_0")
        source_out.disconnect_from(ing_in)

        assert len(consumer.ingredients) == 0
        assert history.can_undo
        handler.disconnect()


class TestOrphanIngredientInteraction:
    """Orphan nodes (model_ref=None) must not crash connect/disconnect handlers."""

    def test_connect_from_orphan_adds_ingredient_from_property(self, graph):
        """Connecting orphan output -> recipe ingredient seeds Ingredient
        from the orphan's item_id property, even though it has no model_ref."""
        from craftgraph.qt_nodes import IDENTIFIER

        consumer = ModifiedRecipe(item_id="Alloy")
        pf = _make_parsed_file(modified_recipes=[consumer])
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])
            orphan = graph.create_node(
                f"{IDENTIFIER}.OrphanIngredientNode", name="Copper"
            )
            orphan.set_property("item_id", "Copper")

        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
        )

        orphan_out = orphan.get_output("output")
        ing_in = m2n[id(consumer)].get_input("ingredient_0")
        orphan_out.connect_to(ing_in)

        assert len(consumer.ingredients) == 1
        assert consumer.ingredients[0].item_id == "Copper"
        assert consumer.ingredients[0].required == 1
        handler.disconnect()

    def test_disconnect_from_orphan_is_noop(self, graph):
        """Disconnecting orphan from recipe does not crash or modify model."""
        from craftgraph.qt_nodes import IDENTIFIER

        consumer = ModifiedRecipe(
            item_id="Ring",
            ingredients=[Ingredient(item_id="Copper", required=2)],
        )
        pf = _make_parsed_file(modified_recipes=[consumer])
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])
            orphan = graph.create_node(
                f"{IDENTIFIER}.OrphanIngredientNode", name="Copper"
            )
            orphan.set_property("item_id", "Copper")
            orphan_out = orphan.get_output("output")
            ing_in = m2n[id(consumer)].get_input("ingredient_0")
            orphan_out.connect_to(ing_in)

        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
        )

        # Disconnect
        orphan_out = orphan.get_output("output")
        ing_in = m2n[id(consumer)].get_input("ingredient_0")
        orphan_out.disconnect_from(ing_in)

        # model_ref is None on orphan -> handler returns early
        assert len(consumer.ingredients) == 1  # unchanged
        assert not history.can_undo
        handler.disconnect()


class TestUIToModelHierarchyPorts:
    def test_connect_nests_tab_in_fab(self, graph):
        """Connecting fab children -> tab parent nests the tab."""
        tab = CraftingTab(tab_id="Potions")
        fab = CustomFabricator(item_id="Fab")
        pf = _make_parsed_file(
            custom_fabricators=[fab],
            crafting_tabs=[tab],
        )
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])

        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
        )

        fab_out = m2n[id(fab)].get_output("tabs_out")
        tab_in = m2n[id(tab)].get_input("parent")
        fab_out.connect_to(tab_in)

        assert tab in fab.tabs
        assert tab not in pf.crafting_tabs
        assert history.can_undo
        handler.disconnect()

    def test_connect_nests_recipe_in_fab(self, graph):
        """Connecting fab added_out -> recipe hierarchy nests the recipe."""
        recipe = AddedRecipe(item_id="Potion")
        fab = CustomFabricator(item_id="Fab")
        pf = _make_parsed_file(
            custom_fabricators=[fab],
            added_recipes=[recipe],
        )
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])

        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
        )

        fab_out = m2n[id(fab)].get_output("added_out")
        hier_in = m2n[id(recipe)].get_input("hierarchy")
        fab_out.connect_to(hier_in)

        assert recipe in fab.added_recipes
        assert recipe not in pf.added_recipes
        assert history.can_undo
        handler.disconnect()


# ---------------------------------------------------------------------------
# Pre-link cycle detection (Step M7.7)
# ---------------------------------------------------------------------------


class TestCycleDetection:
    """Verify that ingredient connections creating cycles are rejected."""

    def test_would_create_cycle_detects_direct_cycle(self, graph, qapp):
        """A -> B -> A is detected as a cycle."""
        recipe_a = ModifiedRecipe(
            item_id="A",
            ingredients=[Ingredient(item_id="B", required=1)],
        )
        recipe_b = ModifiedRecipe(item_id="B")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            modified_recipes=[recipe_a, recipe_b],
        )
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])

        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
        )

        # B -> A would create A -> B -> A cycle
        assert handler.would_create_cycle("B", "A")
        # B -> C would not create a cycle (C doesn't exist)
        assert not handler.would_create_cycle("B", "C")
        handler.disconnect()

    def test_would_create_cycle_detects_transitive_cycle(self, graph, qapp):
        """A -> B -> C -> A is detected as a cycle."""
        recipe_a = ModifiedRecipe(
            item_id="A",
            ingredients=[Ingredient(item_id="B", required=1)],
        )
        recipe_b = ModifiedRecipe(
            item_id="B",
            ingredients=[Ingredient(item_id="C", required=1)],
        )
        recipe_c = ModifiedRecipe(item_id="C")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            modified_recipes=[recipe_a, recipe_b, recipe_c],
        )
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])

        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
        )

        # C -> A would create A -> B -> C -> A cycle
        assert handler.would_create_cycle("C", "A")
        # C -> D would not create a cycle
        assert not handler.would_create_cycle("C", "D")
        handler.disconnect()

    def test_cycle_rejected_callback_fires(self, graph, qapp):
        """When a cycle is rejected, the on_cycle_rejected callback fires."""
        recipe_a = ModifiedRecipe(
            item_id="Alpha",
            ingredients=[Ingredient(item_id="Beta", required=1)],
        )
        recipe_b = ModifiedRecipe(item_id="Beta")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            modified_recipes=[recipe_a, recipe_b],
        )
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])
            connect_ingredients(graph, [pf], m2n)

        rejected: list[tuple[str, str, list[str]]] = []

        def on_rejected(consumer: str, ingredient: str, cycle_path: list[str]) -> None:
            rejected.append((consumer, ingredient, cycle_path))

        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
            on_cycle_rejected=on_rejected,
        )

        # Try to connect Beta -> Alpha (would create Alpha -> Beta -> Alpha)
        beta_out = m2n[id(recipe_b)].get_output("output")
        alpha_ing = [
            p
            for p in m2n[id(recipe_b)].input_ports()
            if p.name().startswith("ingredient_") and not p.connected_ports()
        ]
        if alpha_ing:
            # Actually need to connect Beta's output to Alpha's ingredient port
            # to trigger the cycle. Alpha already has Beta as ingredient.
            # So connect Alpha's output to Beta's ingredient port.
            alpha_out = m2n[id(recipe_a)].get_output("output")
            beta_free_ing = [
                p
                for p in m2n[id(recipe_b)].input_ports()
                if p.name().startswith("ingredient_") and not p.connected_ports()
            ]
            if beta_free_ing:
                alpha_out.connect_to(beta_free_ing[0])

        assert len(rejected) == 1
        assert rejected[0][0] == "Beta"
        assert rejected[0][1] == "Alpha"
        # Callback receives the cycle path as third argument
        cycle_path = rejected[0][2]
        assert isinstance(cycle_path, list)
        assert len(cycle_path) >= 2
        # The cycle must contain both nodes
        assert "Alpha" in cycle_path
        assert "Beta" in cycle_path
        # No command should have been executed
        assert not history.can_undo
        # Model must be unchanged: Beta still has no ingredients
        assert len(recipe_b.ingredients) == 0
        # Alpha's original ingredient list is untouched
        assert len(recipe_a.ingredients) == 1
        assert recipe_a.ingredients[0].item_id == "Beta"
        handler.disconnect()

    def test_cycle_rejection_leaves_model_pristine(self, graph, qapp):
        """Model ingredient lists are completely unchanged after rejection."""
        recipe_a = ModifiedRecipe(
            item_id="X",
            ingredients=[Ingredient(item_id="Y", required=2)],
        )
        recipe_b = ModifiedRecipe(item_id="Y")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            modified_recipes=[recipe_a, recipe_b],
        )
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])
            connect_ingredients(graph, [pf], m2n)

        rejected: list[tuple[str, str]] = []
        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
            on_cycle_rejected=lambda c, i, p: rejected.append((c, i)),
        )

        # Snapshot model state before the cyclic attempt
        a_ings_before = list(recipe_a.ingredients)
        b_ings_before = list(recipe_b.ingredients)

        # Try Y -> X (would create X -> Y -> X cycle)
        x_out = m2n[id(recipe_a)].get_output("output")
        y_free = [
            p
            for p in m2n[id(recipe_b)].input_ports()
            if p.name().startswith("ingredient_") and not p.connected_ports()
        ]
        if y_free:
            x_out.connect_to(y_free[0])

        # Rejection fired, model identical to snapshot
        assert len(rejected) == 1
        assert recipe_a.ingredients == a_ings_before
        assert recipe_b.ingredients == b_ings_before
        assert not history.can_undo
        handler.disconnect()

    def test_non_cyclic_connection_accepted(self, graph, qapp):
        """A valid (non-cyclic) ingredient connection is accepted normally."""
        recipe_a = ModifiedRecipe(item_id="Foo")
        recipe_b = ModifiedRecipe(item_id="Bar")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            modified_recipes=[recipe_a, recipe_b],
        )
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])

        rejected: list[tuple[str, str]] = []
        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
            on_cycle_rejected=lambda c, i, p: rejected.append((c, i)),
        )

        # Connect Bar's output to Foo's ingredient port (no cycle)
        bar_out = m2n[id(recipe_b)].get_output("output")
        foo_ing = [
            p
            for p in m2n[id(recipe_a)].input_ports()
            if p.name().startswith("ingredient_") and not p.connected_ports()
        ]
        bar_out.connect_to(foo_ing[0])

        assert len(rejected) == 0
        assert history.can_undo
        assert len(recipe_a.ingredients) == 1
        assert recipe_a.ingredients[0].item_id == "Bar"
        handler.disconnect()

    def test_warn_before_cycles_disabled_allows_cycle(self, graph, qapp):
        """When warn_before_cycles is False, cyclic connections are accepted."""
        recipe_a = ModifiedRecipe(
            item_id="Alpha",
            ingredients=[Ingredient(item_id="Beta", required=1)],
        )
        recipe_b = ModifiedRecipe(item_id="Beta")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            modified_recipes=[recipe_a, recipe_b],
        )
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])
            connect_ingredients(graph, [pf], m2n)

        rejected: list[tuple[str, str]] = []
        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
            on_cycle_rejected=lambda c, i, p: rejected.append((c, i)),
        )
        handler.warn_before_cycles = False

        # Try to connect Alpha's output to Beta's ingredient (would be a cycle)
        alpha_out = m2n[id(recipe_a)].get_output("output")
        beta_free = [
            p
            for p in m2n[id(recipe_b)].input_ports()
            if p.name().startswith("ingredient_") and not p.connected_ports()
        ]
        if beta_free:
            alpha_out.connect_to(beta_free[0])

        # Cycle was NOT rejected -- connection goes through
        assert len(rejected) == 0
        assert history.can_undo
        assert len(recipe_b.ingredients) == 1
        assert recipe_b.ingredients[0].item_id == "Alpha"
        handler.disconnect()


# ---------------------------------------------------------------------------
# Cycle edge highlighting (Step M7.7)
# ---------------------------------------------------------------------------


class TestCycleEdgeHighlighting:
    """Verify that cycle edges are colored red after loading."""

    def test_highlight_returns_zero_for_acyclic(self, graph, qapp):
        """No cycles found means return 0 and no pipes colored."""
        recipe = ModifiedRecipe(
            item_id="A",
            ingredients=[Ingredient(item_id="B", required=1)],
        )
        pf = ParsedFile(
            source_path=Path("test.txt"),
            modified_recipes=[recipe],
        )

        with SyncGuard()():
            m2n = populate_graph(graph, [pf])
            connect_ingredients(graph, [pf], m2n)
            count = highlight_cycle_edges(graph, [pf], m2n)

        assert count == 0

    def test_highlight_returns_cycle_count(self, graph, qapp):
        """Cycle count is returned correctly."""
        recipe_a = ModifiedRecipe(
            item_id="X",
            ingredients=[Ingredient(item_id="Y", required=1)],
        )
        recipe_b = ModifiedRecipe(
            item_id="Y",
            ingredients=[Ingredient(item_id="X", required=1)],
        )
        pf = ParsedFile(
            source_path=Path("test.txt"),
            modified_recipes=[recipe_a, recipe_b],
        )

        with SyncGuard()():
            m2n = populate_graph(graph, [pf])
            connect_ingredients(graph, [pf], m2n)
            count = highlight_cycle_edges(graph, [pf], m2n)

        assert count >= 1

    def test_cycle_pipe_gets_red_color(self, graph, qapp):
        """Pipes participating in a cycle are styled with the red color."""
        from craftgraph.sync import _CYCLE_COLOR

        recipe_a = ModifiedRecipe(
            item_id="CycA",
            ingredients=[Ingredient(item_id="CycB", required=1)],
        )
        recipe_b = ModifiedRecipe(
            item_id="CycB",
            ingredients=[Ingredient(item_id="CycA", required=1)],
        )
        pf = ParsedFile(
            source_path=Path("test.txt"),
            modified_recipes=[recipe_a, recipe_b],
        )

        with SyncGuard()():
            m2n = populate_graph(graph, [pf])
            connect_ingredients(graph, [pf], m2n)
            highlight_cycle_edges(graph, [pf], m2n)

        viewer = graph.viewer()
        ingredient_pipes = [
            p for p in viewer.all_pipes() if p.input_port.name.startswith("ingredient_")
        ]
        assert len(ingredient_pipes) > 0
        # At least one pipe should have the cycle color
        red_pipes = [p for p in ingredient_pipes if p.color == _CYCLE_COLOR]
        assert len(red_pipes) > 0

    def test_orphan_edges_never_highlighted_as_cycle(self, graph, qapp):
        """Orphan -> recipe edges are never colored red, even with cycles present."""
        from craftgraph.sync import _CYCLE_COLOR, _DEFAULT_PIPE_COLOR

        # Cycle: A -> B -> A. Plus orphan: Copper -> A
        recipe_a = ModifiedRecipe(
            item_id="CycA",
            ingredients=[
                Ingredient(item_id="CycB", required=1),
                Ingredient(item_id="Copper", required=1),
            ],
        )
        recipe_b = ModifiedRecipe(
            item_id="CycB",
            ingredients=[Ingredient(item_id="CycA", required=1)],
        )
        pf = ParsedFile(
            source_path=Path("test.txt"),
            modified_recipes=[recipe_a, recipe_b],
        )

        with SyncGuard()():
            m2n = populate_graph(graph, [pf])
            result = connect_ingredients(graph, [pf], m2n)
            highlight_cycle_edges(graph, [pf], m2n)

        assert "copper" in result.orphan_nodes

        viewer = graph.viewer()
        ingredient_pipes = [
            p for p in viewer.all_pipes() if p.input_port.name.startswith("ingredient_")
        ]

        # Find the orphan pipe (connects to the Copper orphan)
        orphan_node_id = result.orphan_nodes["copper"].id
        orphan_pipes = [
            p for p in ingredient_pipes
            if p.output_port.node.id == orphan_node_id
        ]
        assert len(orphan_pipes) > 0
        for p in orphan_pipes:
            assert p.color == _DEFAULT_PIPE_COLOR


# ---------------------------------------------------------------------------
# Node issue overlays (warning triangles)
# ---------------------------------------------------------------------------


class TestNodeIssueOverlays:
    """Verify warning-triangle overlays appear on nodes with issues."""

    def test_acyclic_clean_no_overlays(self, graph, qapp):
        """Clean acyclic recipes with known ingredients get no warnings."""
        recipe = ModifiedRecipe(
            item_id="A",
            ingredients=[Ingredient(item_id="B", required=1)],
        )
        pf = ParsedFile(source_path=Path("test.txt"), modified_recipes=[recipe])

        with SyncGuard()():
            m2n = populate_graph(graph, [pf])
            connect_ingredients(graph, [pf], m2n)
            errors, warnings = update_node_issue_overlays(
                graph, [pf], m2n, frozenset({"a", "b"}),
            )

        assert errors == 0
        assert warnings == 0
        node = m2n[id(recipe)]
        assert node._warning_overlay is None or not node._warning_overlay.isVisible()

    def test_cycle_member_gets_error_overlay(self, graph, qapp):
        """Recipes participating in a cycle get the red error overlay."""
        recipe_a = ModifiedRecipe(
            item_id="CycA",
            ingredients=[Ingredient(item_id="CycB", required=1)],
        )
        recipe_b = ModifiedRecipe(
            item_id="CycB",
            ingredients=[Ingredient(item_id="CycA", required=1)],
        )
        pf = ParsedFile(
            source_path=Path("test.txt"),
            modified_recipes=[recipe_a, recipe_b],
        )

        with SyncGuard()():
            m2n = populate_graph(graph, [pf])
            connect_ingredients(graph, [pf], m2n)
            errors, _ = update_node_issue_overlays(
                graph, [pf], m2n, frozenset({"cyca", "cycb"}),
            )

        assert errors >= 2
        for recipe in (recipe_a, recipe_b):
            node = m2n[id(recipe)]
            assert node._warning_overlay is not None
            assert node._warning_overlay.isVisible()
            assert node._warning_overlay._severity == "error"

    def test_unknown_ingredient_gets_warning_overlay(self, graph, qapp):
        """Recipe with unknown ingredient ID gets the yellow warning overlay."""
        recipe = ModifiedRecipe(
            item_id="WidgetCraft",
            ingredients=[Ingredient(item_id="MysteryAlloy", required=1)],
        )
        pf = ParsedFile(source_path=Path("test.txt"), modified_recipes=[recipe])

        with SyncGuard()():
            m2n = populate_graph(graph, [pf])
            connect_ingredients(graph, [pf], m2n)
            errors, warnings = update_node_issue_overlays(
                graph, [pf], m2n, frozenset({"widgetcraft"}),
            )

        assert errors == 0
        assert warnings == 1
        node = m2n[id(recipe)]
        assert node._warning_overlay is not None
        assert node._warning_overlay.isVisible()
        assert node._warning_overlay._severity == "warning"

    def test_clear_when_issue_resolved(self, graph, qapp):
        """Re-running with the previously-unknown ingredient now known clears the overlay."""
        recipe = ModifiedRecipe(
            item_id="WidgetCraft",
            ingredients=[Ingredient(item_id="Alloy", required=1)],
        )
        pf = ParsedFile(source_path=Path("test.txt"), modified_recipes=[recipe])

        with SyncGuard()():
            m2n = populate_graph(graph, [pf])
            connect_ingredients(graph, [pf], m2n)
            update_node_issue_overlays(
                graph, [pf], m2n, frozenset({"widgetcraft"}),
            )
            update_node_issue_overlays(
                graph, [pf], m2n, frozenset({"widgetcraft", "alloy"}),
            )

        node = m2n[id(recipe)]
        assert node._warning_overlay is None or not node._warning_overlay.isVisible()


# ---------------------------------------------------------------------------
# Child count labels
# ---------------------------------------------------------------------------


class TestUpdateChildCountLabels:
    def test_fabricator_shows_child_count(self, graph):
        """Fabricator 'tabs_out' port label shows connected count."""
        fab = CustomFabricator(item_id="TestFab")
        tab = CraftingTab(tab_id="Tab1", display_name="Tab 1")
        fab.tabs.append(tab)

        pf = _make_parsed_file(custom_fabricators=[fab])

        with SyncGuard()():
            m2n = populate_graph(graph, [pf])
            connect_hierarchy(graph, [pf], m2n)
            update_child_count_labels(m2n)

        fab_node = m2n[id(fab)]
        port = fab_node.get_output("tabs_out")
        text_item = fab_node.view.get_output_text_item(port.view)
        assert text_item.toPlainText() == "tabs_out (1)"

    def test_fabricator_multiple_children(self, graph):
        """Fabricator typed port labels reflect connected counts per type."""
        fab = CustomFabricator(item_id="MultiFab")
        tab1 = CraftingTab(tab_id="T1", display_name="T1")
        tab2 = CraftingTab(tab_id="T2", display_name="T2")
        recipe = AddedRecipe(item_id="R1", path="MultiFab")
        fab.tabs.extend([tab1, tab2])
        fab.added_recipes.append(recipe)

        pf = _make_parsed_file(custom_fabricators=[fab])

        with SyncGuard()():
            m2n = populate_graph(graph, [pf])
            connect_hierarchy(graph, [pf], m2n)
            update_child_count_labels(m2n)

        fab_node = m2n[id(fab)]
        # tabs_out should show 2 tabs connected
        tabs_port = fab_node.get_output("tabs_out")
        tabs_text = fab_node.view.get_output_text_item(tabs_port.view)
        assert tabs_text.toPlainText() == "tabs_out (2)"
        # added_out should show 1 recipe connected
        added_port = fab_node.get_output("added_out")
        added_text = fab_node.view.get_output_text_item(added_port.view)
        assert added_text.toPlainText() == "added_out (1)"

    def test_tab_shows_child_count(self, graph):
        """CraftingTab 'children' port label shows connected count."""
        fab = CustomFabricator(item_id="TabFab")
        parent_tab = CraftingTab(tab_id="Parent", display_name="Parent")
        child_tab = CraftingTab(
            tab_id="Child",
            display_name="Child",
            parent_tab_path="Parent",
        )
        fab.tabs.extend([parent_tab, child_tab])

        pf = _make_parsed_file(custom_fabricators=[fab])

        with SyncGuard()():
            m2n = populate_graph(graph, [pf])
            connect_hierarchy(graph, [pf], m2n)
            update_child_count_labels(m2n)

        parent_node = m2n[id(parent_tab)]
        port = parent_node.get_output("children")
        text_item = parent_node.view.get_output_text_item(port.view)
        assert text_item.toPlainText() == "children (1)"

    def test_no_children_shows_plain_label(self, graph):
        """Fabricator with zero connections shows port names without count."""
        fab = CustomFabricator(item_id="EmptyFab")
        pf = _make_parsed_file(custom_fabricators=[fab])

        with SyncGuard()():
            m2n = populate_graph(graph, [pf])
            update_child_count_labels(m2n)

        fab_node = m2n[id(fab)]
        port = fab_node.get_output("tabs_out")
        text_item = fab_node.view.get_output_text_item(port.view)
        assert text_item.toPlainText() == "tabs_out"

    def test_non_container_nodes_unaffected(self, graph):
        """Recipe nodes (no 'children' port) are skipped without error."""
        recipe = ModifiedRecipe(item_id="Plain")
        pf = _make_parsed_file(modified_recipes=[recipe])

        with SyncGuard()():
            m2n = populate_graph(graph, [pf])
            # Should not raise
            update_child_count_labels(m2n)


# ---------------------------------------------------------------------------
# Recipe reassignment warning (Step 11j)
# ---------------------------------------------------------------------------


class TestRecipeReassignmentWarning:
    """When a recipe with an existing path is connected to a fabricator,
    the on_reassignment_warning callback should fire."""

    def test_warning_fires_when_recipe_has_existing_path(self, graph):
        """A recipe with path='OldFab/Potions' triggers a warning on reassign."""
        recipe = AddedRecipe(item_id="Potion", path="OldFab/Potions")
        fab = CustomFabricator(item_id="NewFab")
        pf = _make_parsed_file(
            custom_fabricators=[fab],
            added_recipes=[recipe],
        )
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])

        captured: list[tuple[str, str]] = []
        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
            on_reassignment_warning=lambda item_id, old_path: captured.append(
                (item_id, old_path)
            ),
        )

        fab_out = m2n[id(fab)].get_output("added_out")
        hier_in = m2n[id(recipe)].get_input("hierarchy")
        fab_out.connect_to(hier_in)

        assert len(captured) == 1
        assert captured[0] == ("Potion", "OldFab/Potions")
        # The nesting still happens despite the warning
        assert recipe in fab.added_recipes
        handler.disconnect()

    def test_no_warning_when_recipe_has_no_path(self, graph):
        """A recipe with empty path does not trigger a warning."""
        recipe = AddedRecipe(item_id="Potion")
        fab = CustomFabricator(item_id="Fab")
        pf = _make_parsed_file(
            custom_fabricators=[fab],
            added_recipes=[recipe],
        )
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])

        captured: list[tuple[str, str]] = []
        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
            on_reassignment_warning=lambda item_id, old_path: captured.append(
                (item_id, old_path)
            ),
        )

        fab_out = m2n[id(fab)].get_output("added_out")
        hier_in = m2n[id(recipe)].get_input("hierarchy")
        fab_out.connect_to(hier_in)

        assert len(captured) == 0
        assert recipe in fab.added_recipes
        handler.disconnect()

    def test_no_warning_without_callback(self, graph):
        """Without on_reassignment_warning callback, no error on reassign."""
        recipe = AddedRecipe(item_id="Potion", path="OldFab/Potions")
        fab = CustomFabricator(item_id="NewFab")
        pf = _make_parsed_file(
            custom_fabricators=[fab],
            added_recipes=[recipe],
        )
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])

        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
        )

        fab_out = m2n[id(fab)].get_output("added_out")
        hier_in = m2n[id(recipe)].get_input("hierarchy")
        fab_out.connect_to(hier_in)

        # Nesting proceeds without error
        assert recipe in fab.added_recipes
        handler.disconnect()


# ---------------------------------------------------------------------------
# Tab-to-tab cycle detection (Step 11j)
# ---------------------------------------------------------------------------


class TestTabToTabCycleCheck:
    """Detect cycles in the tab parent chain when connecting tabs."""

    def test_direct_tab_cycle_rejected(self, graph, qapp):
        """Tab A -> children -> Tab B -> children -> Tab A is rejected."""
        tab_a = CraftingTab(tab_id="TabA", parent_tab_path="Fab")
        tab_b = CraftingTab(tab_id="TabB", parent_tab_path="TabA")
        fab = CustomFabricator(item_id="Fab", tabs=[tab_a, tab_b])
        pf = _make_parsed_file(custom_fabricators=[fab])
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])
            connect_hierarchy(graph, [pf], m2n)

        rejected: list[tuple[str, str]] = []
        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
            on_cycle_rejected=lambda c, i, p: rejected.append((c, i)),
        )

        # Tab B already has parent_tab_path="TabA" (B is child of A).
        # Connecting Tab B's children -> Tab A's parent would create A->B->A.
        # Tab A is currently connected to Fab. The connect_to will first
        # disconnect Tab A from Fab (NodeGraphQt auto-disconnects single-input
        # ports), then connect to Tab B. Both fire signals.
        b_children = m2n[id(tab_b)].get_output("children")
        a_parent = m2n[id(tab_a)].get_input("parent")
        b_children.connect_to(a_parent)

        assert len(rejected) == 1
        # Tab A's parent_tab_path should NOT be changed to TabB
        assert tab_a.parent_tab_path != "TabB"
        handler.disconnect()

    def test_valid_tab_nesting_allowed(self, graph, qapp):
        """Connecting Tab C under Tab A (no cycle) succeeds."""
        tab_a = CraftingTab(tab_id="TabA", parent_tab_path="Fab")
        tab_c = CraftingTab(tab_id="TabC", parent_tab_path="Fab")
        fab = CustomFabricator(item_id="Fab", tabs=[tab_a, tab_c])
        pf = _make_parsed_file(custom_fabricators=[fab])
        guard = SyncGuard()
        history = EditHistory()

        with guard():
            m2n = populate_graph(graph, [pf])
            connect_hierarchy(graph, [pf], m2n)

        rejected: list[tuple[str, str]] = []
        handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[pf],
            on_cycle_rejected=lambda c, i, p: rejected.append((c, i)),
        )

        # Disconnect Tab C from fab, then connect under Tab A
        c_parent = m2n[id(tab_c)].get_input("parent")
        for port in c_parent.connected_ports():
            port.disconnect_from(c_parent)

        a_children = m2n[id(tab_a)].get_output("children")
        a_children.connect_to(c_parent)

        assert len(rejected) == 0
        # Tab C's parent_tab_path should be updated to TabA
        assert tab_c.parent_tab_path == "TabA"
        handler.disconnect()


# ---------------------------------------------------------------------------
# Save/export validation summary (Step 11j)
# ---------------------------------------------------------------------------


class TestValidateBeforeSave:
    """Pure-model validation that runs before writing files to disk."""

    def test_no_issues_on_valid_file(self):
        """A well-formed parsed file returns no issues."""
        from craftgraph.sync import validate_parsed_files

        recipe = AddedRecipe(
            item_id="bigwater",
            ingredients=[Ingredient(item_id="bleach", required=1)],
            path="Fabricator/Resources",
        )
        pf = _make_parsed_file(added_recipes=[recipe])
        known_ids = frozenset({"bigwater", "bleach"})

        issues = validate_parsed_files([pf], known_ids)
        assert issues == []

    def test_unknown_ingredient_id_flagged(self):
        """An ingredient referencing an unknown ID is flagged."""
        from craftgraph.sync import validate_parsed_files

        recipe = ModifiedRecipe(
            item_id="titanium",
            ingredients=[Ingredient(item_id="unobtainium", required=1)],
        )
        pf = _make_parsed_file(modified_recipes=[recipe])
        known_ids = frozenset({"titanium"})

        issues = validate_parsed_files([pf], known_ids)
        assert len(issues) == 1
        assert "unobtainium" in issues[0].lower()

    def test_missing_parent_tab_path_flagged(self):
        """A tab with parent_tab_path referencing a non-existent tab is flagged."""
        from craftgraph.sync import validate_parsed_files

        tab = CraftingTab(tab_id="Potions", parent_tab_path="MissingTab")
        fab = CustomFabricator(item_id="Fab", tabs=[tab])
        pf = _make_parsed_file(custom_fabricators=[fab])

        issues = validate_parsed_files([pf], frozenset())
        assert len(issues) == 1
        assert "MissingTab" in issues[0]

    def test_valid_parent_tab_path_not_flagged(self):
        """A tab referencing its fabricator ID as parent is valid."""
        from craftgraph.sync import validate_parsed_files

        tab = CraftingTab(tab_id="Potions", parent_tab_path="Fab")
        fab = CustomFabricator(item_id="Fab", tabs=[tab])
        pf = _make_parsed_file(custom_fabricators=[fab])

        issues = validate_parsed_files([pf], frozenset())
        assert issues == []

    def test_recipe_path_referencing_missing_tab_flagged(self):
        """A recipe with a path pointing to a non-existent tab is flagged."""
        from craftgraph.sync import validate_parsed_files

        recipe = AddedRecipe(item_id="potion", path="Fab/MissingTab")
        fab = CustomFabricator(item_id="Fab", added_recipes=[recipe])
        pf = _make_parsed_file(custom_fabricators=[fab])

        issues = validate_parsed_files([pf], frozenset({"potion"}))
        assert len(issues) == 1
        assert "MissingTab" in issues[0]

    def test_recipe_path_referencing_valid_tab_not_flagged(self):
        """A recipe with a valid tab path is not flagged."""
        from craftgraph.sync import validate_parsed_files

        tab = CraftingTab(tab_id="Resources", parent_tab_path="Fab")
        recipe = AddedRecipe(item_id="potion", path="Fab/Resources")
        fab = CustomFabricator(
            item_id="Fab", tabs=[tab], added_recipes=[recipe],
        )
        pf = _make_parsed_file(custom_fabricators=[fab])

        issues = validate_parsed_files([pf], frozenset({"potion"}))
        assert issues == []

    def test_multiple_issues_collected(self):
        """Multiple issues across files are all returned."""
        from craftgraph.sync import validate_parsed_files

        recipe = ModifiedRecipe(
            item_id="gold",
            ingredients=[
                Ingredient(item_id="unknown1", required=1),
                Ingredient(item_id="unknown2", required=2),
            ],
        )
        pf = _make_parsed_file(modified_recipes=[recipe])

        issues = validate_parsed_files([pf], frozenset({"gold"}))
        assert len(issues) == 2
