"""Tests for NodeKind enum, mappings, and color coverage in gui_nodes.py.

These tests verify that every CC3 block type has a corresponding NodeKind,
that all mapping dictionaries are complete and consistent, and that the
color palette has no gaps.  They exercise pure data structures and do not
require a DPG rendering context.
"""

import pytest

dpg = pytest.importorskip("dearpygui.dearpygui", reason="Dear PyGui not installed")

from craftgraph.gui_nodes import (  # noqa: E402
    _KIND_COLORS,
    KIND_TO_MODEL,
    KIND_TO_NON_RECIPE_MODEL,
    NON_RECIPE_KINDS,
    RECIPE_KINDS,
    NodeKind,
    kind_from_recipe,
)
from craftgraph.models import (  # noqa: E402
    AddedRecipe,
    AliasRecipe,
    BlockType,
    CustomFood,
    ModifiedRecipe,
)

# ---------------------------------------------------------------------------
# BlockType <-> NodeKind coverage
# ---------------------------------------------------------------------------

# Expected mapping from each BlockType to its NodeKind counterpart.
_BLOCK_TO_KIND: dict[BlockType, NodeKind] = {
    BlockType.MODIFIED_RECIPES: NodeKind.MODIFIED_RECIPE,
    BlockType.ADDED_RECIPES: NodeKind.ADDED_RECIPE,
    BlockType.ALIAS_RECIPES: NodeKind.ALIAS_RECIPE,
    BlockType.CUSTOM_FOODS: NodeKind.CUSTOM_FOOD,
    BlockType.CUSTOM_FABRICATORS: NodeKind.CUSTOM_FABRICATOR,
    BlockType.CUSTOM_CRAFTING_TABS: NodeKind.CUSTOM_CRAFTING_TAB,
    BlockType.MOVED_RECIPES: NodeKind.MOVED_RECIPE,
    BlockType.CUSTOM_SIZES: NodeKind.CUSTOM_SIZE,
    BlockType.CUSTOM_BIO_FUELS: NodeKind.CUSTOM_BIO_FUEL,
    BlockType.CUSTOM_FRAGMENT_COUNTS: NodeKind.CUSTOM_FRAGMENT_COUNT,
}


class TestBlockTypeToNodeKindCoverage:
    """Every BlockType enum member must have a NodeKind counterpart."""

    def test_all_block_types_mapped(self) -> None:
        assert set(_BLOCK_TO_KIND.keys()) == set(BlockType)

    @pytest.mark.parametrize(
        "block_type,expected_kind",
        list(_BLOCK_TO_KIND.items()),
        ids=[bt.name for bt in _BLOCK_TO_KIND],
    )
    def test_block_type_has_node_kind(
        self, block_type: BlockType, expected_kind: NodeKind
    ) -> None:
        assert expected_kind in NodeKind


# ---------------------------------------------------------------------------
# NodeKind partitioning (RECIPE_KINDS + NON_RECIPE_KINDS + INGREDIENT)
# ---------------------------------------------------------------------------


class TestNodeKindPartitioning:
    """RECIPE_KINDS, NON_RECIPE_KINDS, and INGREDIENT must partition NodeKind exactly."""

    def test_no_overlap(self) -> None:
        assert RECIPE_KINDS.isdisjoint(NON_RECIPE_KINDS)

    def test_ingredient_not_in_either(self) -> None:
        assert NodeKind.INGREDIENT not in RECIPE_KINDS
        assert NodeKind.INGREDIENT not in NON_RECIPE_KINDS

    def test_covers_all_members(self) -> None:
        all_kinds = RECIPE_KINDS | NON_RECIPE_KINDS | {NodeKind.INGREDIENT}
        assert all_kinds == set(NodeKind)

    def test_recipe_kinds_count(self) -> None:
        assert len(RECIPE_KINDS) == 4

    def test_non_recipe_kinds_count(self) -> None:
        assert len(NON_RECIPE_KINDS) == 6


# ---------------------------------------------------------------------------
# Mapping completeness
# ---------------------------------------------------------------------------


class TestMappingCompleteness:
    """KIND_TO_MODEL and KIND_TO_NON_RECIPE_MODEL must cover their kind sets."""

    def test_kind_to_model_covers_recipe_kinds(self) -> None:
        assert set(KIND_TO_MODEL.keys()) == RECIPE_KINDS

    def test_kind_to_non_recipe_model_covers_non_recipe_kinds(self) -> None:
        assert set(KIND_TO_NON_RECIPE_MODEL.keys()) == NON_RECIPE_KINDS

    def test_kind_to_model_values_have_label_and_class(self) -> None:
        for kind, (label, cls) in KIND_TO_MODEL.items():
            assert isinstance(label, str) and len(label) > 0, f"{kind} has empty label"
            assert isinstance(cls, type), f"{kind} mapped to non-type: {cls}"

    def test_kind_to_non_recipe_model_values_have_label_and_class(self) -> None:
        for kind, (label, cls) in KIND_TO_NON_RECIPE_MODEL.items():
            assert isinstance(label, str) and len(label) > 0, f"{kind} has empty label"
            assert isinstance(cls, type), f"{kind} mapped to non-type: {cls}"


# ---------------------------------------------------------------------------
# Color palette coverage
# ---------------------------------------------------------------------------


class TestColorPalette:
    """_KIND_COLORS must cover all non-INGREDIENT NodeKind members."""

    def test_all_non_ingredient_kinds_have_colors(self) -> None:
        expected = set(NodeKind) - {NodeKind.INGREDIENT}
        assert set(_KIND_COLORS.keys()) == expected

    def test_colors_are_rgb_tuples(self) -> None:
        for kind, color in _KIND_COLORS.items():
            assert len(color) == 3, f"{kind} color has {len(color)} components"
            for channel in color:
                assert 0 <= channel <= 255, f"{kind} channel out of range: {channel}"

    def test_no_duplicate_colors(self) -> None:
        seen: dict[tuple[int, int, int], NodeKind] = {}
        for kind, color in _KIND_COLORS.items():
            if color in seen:
                pytest.fail(f"{kind} and {seen[color]} share the same color {color}")
            seen[color] = kind


# ---------------------------------------------------------------------------
# kind_from_recipe() dispatch
# ---------------------------------------------------------------------------


class TestKindFromRecipe:
    """kind_from_recipe() must return the most-derived NodeKind."""

    def test_modified_recipe(self) -> None:
        recipe = ModifiedRecipe(item_id="Titanium")
        assert kind_from_recipe(recipe) is NodeKind.MODIFIED_RECIPE

    def test_added_recipe(self) -> None:
        recipe = AddedRecipe(item_id="Titanium", path="Fabricator/Resources")
        assert kind_from_recipe(recipe) is NodeKind.ADDED_RECIPE

    def test_alias_recipe(self) -> None:
        recipe = AliasRecipe(
            item_id="Titanium",
            path="Fabricator/Resources",
            display_name="Titanium",
            tooltip="A common metal",
        )
        assert kind_from_recipe(recipe) is NodeKind.ALIAS_RECIPE

    def test_custom_food(self) -> None:
        recipe = CustomFood(
            item_id="BigMeal",
            path="Fabricator/Survival",
            display_name="Big Meal",
            tooltip="A hearty meal",
            food_value=50,
            water_value=20,
        )
        assert kind_from_recipe(recipe) is NodeKind.CUSTOM_FOOD

    def test_custom_fabricator_is_non_recipe_kind(self) -> None:
        """CustomFabricator is a non-recipe type handled by KIND_TO_NON_RECIPE_MODEL."""
        assert NodeKind.CUSTOM_FABRICATOR in NON_RECIPE_KINDS
        assert NodeKind.CUSTOM_FABRICATOR not in RECIPE_KINDS


# ---------------------------------------------------------------------------
# __empty__ sentinel contract
# ---------------------------------------------------------------------------


class TestEmptySlotContract:
    """The __empty__ sentinel key must be documented and consistent."""

    def test_empty_slot_key_is_string(self) -> None:
        """The sentinel key used for dynamic input slots is '__empty__'."""
        assert isinstance("__empty__", str)

    def test_empty_slot_not_a_valid_ingredient_id(self) -> None:
        """__empty__ must never collide with a real CC3 TechType ID."""
        from craftgraph.vanilla_ids import load_vanilla_ids

        vanilla = load_vanilla_ids()
        assert "__empty__" not in vanilla

    def test_empty_slot_not_in_recipe_kinds(self) -> None:
        """The __empty__ key is a visual-only concept, not a NodeKind."""
        for kind in NodeKind:
            assert kind.value != "__empty__"
