"""Tests for fabricator/tab/recipe hierarchy connections.

Tests cover:
- NestTabInFabricatorCommand and UnnestTabFromFabricatorCommand round-trips
- NestRecipeInFabricatorCommand and UnnestRecipeFromFabricatorCommand round-trips
- Standalone file hierarchy (ChangeRecipeFieldCommand / ChangeNonRecipeFieldCommand)
- Path construction for nested tabs
"""

from pathlib import Path

from craftgraph.commands import (
    ChangeNonRecipeFieldCommand,
    ChangeRecipeFieldCommand,
    NestRecipeInFabricatorCommand,
    NestTabInFabricatorCommand,
    UnnestRecipeFromFabricatorCommand,
    UnnestTabFromFabricatorCommand,
)
from craftgraph.models import (
    AddedRecipe,
    AliasRecipe,
    BlockType,
    CraftingTab,
    CustomFabricator,
    CustomFood,
    ParsedFile,
)


class TestNestTabRoundTrip:
    """Verify NestTabInFabricatorCommand preserves all data through execute/undo cycles."""

    def test_double_execute_undo_is_stable(self) -> None:
        tab = CraftingTab(tab_id="Weapons", display_name="Weapons Tab")
        fab = CustomFabricator(item_id="AlchemyFab")
        pf = ParsedFile(
            source_path=Path("t.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            crafting_tabs=[tab],
            custom_fabricators=[fab],
        )
        cmd = NestTabInFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab)
        cmd.execute()
        cmd.undo()
        cmd.execute()
        assert tab in fab.tabs
        assert tab not in pf.crafting_tabs
        assert tab.parent_tab_path == "AlchemyFab"

    def test_preserves_display_name(self) -> None:
        tab = CraftingTab(tab_id="Heavy", display_name="Heavy Weapons")
        fab = CustomFabricator(item_id="Fab1")
        pf = ParsedFile(
            source_path=Path("t.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            crafting_tabs=[tab],
            custom_fabricators=[fab],
        )
        cmd = NestTabInFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab)
        cmd.execute()
        assert tab.display_name == "Heavy Weapons"

    def test_nest_then_unnest_round_trip(self) -> None:
        tab = CraftingTab(tab_id="Tools")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("t.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            crafting_tabs=[tab],
            custom_fabricators=[fab],
        )
        # Nest
        nest = NestTabInFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab)
        nest.execute()
        assert tab in fab.tabs
        # Unnest
        unnest = UnnestTabFromFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab)
        unnest.execute()
        assert tab in pf.crafting_tabs
        assert tab not in fab.tabs
        assert tab.parent_tab_path == ""


class TestNestRecipeRoundTrip:
    """Verify NestRecipeInFabricatorCommand preserves data through cycles."""

    def test_recipe_path_set_to_tab_path(self) -> None:
        recipe = AddedRecipe(item_id="LaserGun")
        fab = CustomFabricator(item_id="AlchemyFab")
        pf = ParsedFile(
            source_path=Path("t.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            added_recipes=[recipe],
            custom_fabricators=[fab],
        )
        cmd = NestRecipeInFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
            path="AlchemyFab/Weapons",
        )
        cmd.execute()
        assert recipe.path == "AlchemyFab/Weapons"

    def test_undo_clears_path(self) -> None:
        recipe = AliasRecipe(item_id="QuickBlade")
        fab = CustomFabricator(item_id="Fab1")
        pf = ParsedFile(
            source_path=Path("t.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            alias_recipes=[recipe],
            custom_fabricators=[fab],
        )
        cmd = NestRecipeInFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
            path="Fab1",
        )
        cmd.execute()
        cmd.undo()
        assert recipe.path == ""
        assert recipe in pf.alias_recipes

    def test_nest_then_unnest_round_trip(self) -> None:
        recipe = CustomFood(item_id="SuperMeal")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("t.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_foods=[recipe],
            custom_fabricators=[fab],
        )
        nest = NestRecipeInFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
            path="MyFab",
        )
        nest.execute()
        assert recipe in fab.custom_foods
        unnest = UnnestRecipeFromFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
        )
        unnest.execute()
        assert recipe in pf.custom_foods
        assert recipe not in fab.custom_foods
        assert recipe.path == ""

    def test_multiple_recipes_nested_independently(self) -> None:
        r1 = AddedRecipe(item_id="Gun1")
        r2 = AliasRecipe(item_id="Gun2")
        fab = CustomFabricator(item_id="WeaponFab")
        pf = ParsedFile(
            source_path=Path("t.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            added_recipes=[r1],
            alias_recipes=[r2],
            custom_fabricators=[fab],
        )
        cmd1 = NestRecipeInFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=r1,
            path="WeaponFab",
        )
        cmd2 = NestRecipeInFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=r2,
            path="WeaponFab/Guns",
        )
        cmd1.execute()
        cmd2.execute()
        assert r1 in fab.added_recipes
        assert r2 in fab.alias_recipes
        assert len(pf.added_recipes) == 0
        assert len(pf.alias_recipes) == 0


class TestStandaloneTabRecipeLink:
    """In standalone files, linking sets path fields rather than moving entries."""

    def test_tab_to_recipe_sets_path(self) -> None:
        recipe = AddedRecipe(item_id="HealthPotion")
        cmd = ChangeRecipeFieldCommand(
            recipe=recipe,
            field_name="path",
            new_value="AlchemyFab/Potions",
        )
        cmd.execute()
        assert recipe.path == "AlchemyFab/Potions"

    def test_tab_to_subtab_sets_parent_tab_path(self) -> None:
        child_tab = CraftingTab(tab_id="Heavy")
        cmd = ChangeNonRecipeFieldCommand(
            entry=child_tab,
            field_name="parent_tab_path",
            new_value="Weapons",
        )
        cmd.execute()
        assert child_tab.parent_tab_path == "Weapons"

    def test_clear_path_on_delink(self) -> None:
        recipe = AddedRecipe(item_id="Sword", path="Weapons/Heavy")
        cmd = ChangeRecipeFieldCommand(
            recipe=recipe,
            field_name="path",
            new_value="",
        )
        cmd.execute()
        assert recipe.path == ""
        cmd.undo()
        assert recipe.path == "Weapons/Heavy"

    def test_clear_parent_tab_path_on_delink(self) -> None:
        tab = CraftingTab(tab_id="SubTab", parent_tab_path="Weapons")
        cmd = ChangeNonRecipeFieldCommand(
            entry=tab,
            field_name="parent_tab_path",
            new_value="",
        )
        cmd.execute()
        assert tab.parent_tab_path == ""
        cmd.undo()
        assert tab.parent_tab_path == "Weapons"


class TestTabPathConstruction:
    """Verify correct path string construction for nested tabs."""

    def test_simple_tab_path(self) -> None:
        """A top-level tab's path is just its tab_id."""
        tab = CraftingTab(tab_id="Weapons")
        assert tab.tab_id == "Weapons"
        assert tab.parent_tab_path == ""

    def test_nested_tab_path(self) -> None:
        """A sub-tab gets its parent's full path as parent_tab_path."""
        parent = CraftingTab(tab_id="Weapons")
        child = CraftingTab(tab_id="Heavy")
        cmd = ChangeNonRecipeFieldCommand(
            entry=child,
            field_name="parent_tab_path",
            new_value=parent.tab_id,
        )
        cmd.execute()
        full_path = f"{child.parent_tab_path}/{child.tab_id}"
        assert full_path == "Weapons/Heavy"

    def test_deeply_nested_tab_path(self) -> None:
        """Three levels deep: Weapons/Heavy/Experimental."""
        level2 = CraftingTab(tab_id="Heavy", parent_tab_path="Weapons")
        level3 = CraftingTab(tab_id="Experimental")
        full_parent_path = f"{level2.parent_tab_path}/{level2.tab_id}"
        cmd = ChangeNonRecipeFieldCommand(
            entry=level3,
            field_name="parent_tab_path",
            new_value=full_parent_path,
        )
        cmd.execute()
        full_path = f"{level3.parent_tab_path}/{level3.tab_id}"
        assert full_path == "Weapons/Heavy/Experimental"


class TestNestNonAddedRecipeTypes:
    """Verify that AliasRecipe and CustomFood can be nested in fabricators."""

    def test_alias_recipe_nests_in_fabricator(self) -> None:
        recipe = AliasRecipe(
            item_id="CustomBlade",
            display_name="Custom Blade",
            tooltip="A blade",
        )
        fab = CustomFabricator(item_id="WeaponFab")
        pf = ParsedFile(
            source_path=Path("t.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            alias_recipes=[recipe],
            custom_fabricators=[fab],
        )
        cmd = NestRecipeInFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
            path="WeaponFab",
        )
        cmd.execute()
        assert recipe in fab.alias_recipes
        assert recipe not in pf.alias_recipes
        assert recipe.path == "WeaponFab"

    def test_custom_food_nests_in_fabricator(self) -> None:
        recipe = CustomFood(
            item_id="SuperMeal",
            display_name="Super Meal",
            tooltip="Delicious",
            food_value=50,
        )
        fab = CustomFabricator(item_id="KitchenFab")
        pf = ParsedFile(
            source_path=Path("t.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_foods=[recipe],
            custom_fabricators=[fab],
        )
        cmd = NestRecipeInFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
            path="KitchenFab",
        )
        cmd.execute()
        assert recipe in fab.custom_foods
        assert recipe not in pf.custom_foods
        assert recipe.path == "KitchenFab"
