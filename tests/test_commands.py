"""Tests for the command pattern and edit history.

Tests cover:
- EditHistory: undo/redo stacks, dirty tracking, save index, callbacks
- AddIngredientCommand: append + undo
- RemoveIngredientCommand: remove by index + undo restores position
- ChangeIngredientCommand: swap frozen ingredient + undo
- ChangeRecipeFieldCommand: setattr/getattr for scalar fields
- AddRecipeCommand: add to correct ParsedFile list by type
- RemoveRecipeCommand: remove + undo restores index
- CompoundCommand: grouped execute/undo
- Integration: parse -> apply commands -> verify model state
"""

from pathlib import Path

from craftgraph.commands import (
    AddIngredientCommand,
    AddNonRecipeCommand,
    AddRecipeCommand,
    ChangeIngredientCommand,
    ChangeNonRecipeFieldCommand,
    ChangeRecipeFieldCommand,
    CompoundCommand,
    EditHistory,
    NestRecipeInFabricatorCommand,
    NestTabInFabricatorCommand,
    RemoveIngredientCommand,
    RemoveNonRecipeCommand,
    RemoveRecipeCommand,
    UnnestRecipeFromFabricatorCommand,
    UnnestTabFromFabricatorCommand,
)
from craftgraph.models import (
    AddedRecipe,
    AliasRecipe,
    BlockType,
    CraftingTab,
    CustomBioFuel,
    CustomFabricator,
    CustomFood,
    CustomFragmentCount,
    CustomSize,
    Ingredient,
    ModifiedRecipe,
    MovedRecipe,
    ParsedFile,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_recipe(
    item_id: str = "TestItem",
    ingredients: list[Ingredient] | None = None,
) -> ModifiedRecipe:
    return ModifiedRecipe(
        item_id=item_id,
        ingredients=ingredients or [],
    )


def _make_parsed_file(
    recipes: list[ModifiedRecipe] | None = None,
    *,
    block_type: BlockType = BlockType.MODIFIED_RECIPES,
) -> ParsedFile:
    pf = ParsedFile(source_path=Path("test.txt"), block_type=block_type)
    for recipe in recipes or []:
        if isinstance(recipe, CustomFood):
            pf.custom_foods.append(recipe)
        elif isinstance(recipe, AliasRecipe):
            pf.alias_recipes.append(recipe)
        elif isinstance(recipe, AddedRecipe):
            pf.added_recipes.append(recipe)
        else:
            pf.modified_recipes.append(recipe)
    return pf


# ---------------------------------------------------------------------------
# EditHistory
# ---------------------------------------------------------------------------


class TestEditHistory:
    """Test undo/redo stack management and dirty tracking."""

    def test_initial_state(self) -> None:
        history = EditHistory()
        assert not history.can_undo
        assert not history.can_redo
        assert not history.is_dirty

    def test_execute_enables_undo(self) -> None:
        history = EditHistory()
        recipe = _make_recipe()
        cmd = AddIngredientCommand(recipe, Ingredient("A", 1))
        history.execute(cmd)
        assert history.can_undo
        assert not history.can_redo

    def test_undo_moves_to_redo(self) -> None:
        history = EditHistory()
        recipe = _make_recipe()
        cmd = AddIngredientCommand(recipe, Ingredient("A", 1))
        history.execute(cmd)
        history.undo()
        assert not history.can_undo
        assert history.can_redo

    def test_redo_moves_back_to_undo(self) -> None:
        history = EditHistory()
        recipe = _make_recipe()
        cmd = AddIngredientCommand(recipe, Ingredient("A", 1))
        history.execute(cmd)
        history.undo()
        history.redo()
        assert history.can_undo
        assert not history.can_redo

    def test_new_execute_clears_redo(self) -> None:
        history = EditHistory()
        recipe = _make_recipe()
        history.execute(AddIngredientCommand(recipe, Ingredient("A", 1)))
        history.undo()
        assert history.can_redo
        history.execute(AddIngredientCommand(recipe, Ingredient("B", 1)))
        assert not history.can_redo

    def test_dirty_after_execute(self) -> None:
        history = EditHistory()
        recipe = _make_recipe()
        history.execute(AddIngredientCommand(recipe, Ingredient("A", 1)))
        assert history.is_dirty

    def test_not_dirty_after_mark_saved(self) -> None:
        history = EditHistory()
        recipe = _make_recipe()
        history.execute(AddIngredientCommand(recipe, Ingredient("A", 1)))
        history.mark_saved()
        assert not history.is_dirty

    def test_dirty_again_after_new_edit(self) -> None:
        history = EditHistory()
        recipe = _make_recipe()
        history.execute(AddIngredientCommand(recipe, Ingredient("A", 1)))
        history.mark_saved()
        history.execute(AddIngredientCommand(recipe, Ingredient("B", 1)))
        assert history.is_dirty

    def test_dirty_after_undo_past_save_point(self) -> None:
        history = EditHistory()
        recipe = _make_recipe()
        history.execute(AddIngredientCommand(recipe, Ingredient("A", 1)))
        history.mark_saved()
        history.undo()
        assert history.is_dirty

    def test_clean_after_redo_to_save_point(self) -> None:
        history = EditHistory()
        recipe = _make_recipe()
        history.execute(AddIngredientCommand(recipe, Ingredient("A", 1)))
        history.mark_saved()
        history.undo()
        history.redo()
        assert not history.is_dirty

    def test_on_change_callback_fires(self) -> None:
        call_count = [0]

        def on_change() -> None:
            call_count[0] += 1

        history = EditHistory(on_change=on_change)
        recipe = _make_recipe()
        history.execute(AddIngredientCommand(recipe, Ingredient("A", 1)))
        assert call_count[0] == 1
        history.undo()
        assert call_count[0] == 2
        history.redo()
        assert call_count[0] == 3

    def test_undo_on_empty_is_noop(self) -> None:
        history = EditHistory()
        history.undo()
        assert not history.can_undo

    def test_redo_on_empty_is_noop(self) -> None:
        history = EditHistory()
        history.redo()
        assert not history.can_redo

    def test_clear_resets_everything(self) -> None:
        history = EditHistory()
        recipe = _make_recipe()
        history.execute(AddIngredientCommand(recipe, Ingredient("A", 1)))
        history.mark_saved()
        history.execute(AddIngredientCommand(recipe, Ingredient("B", 1)))
        history.clear()
        assert not history.can_undo
        assert not history.can_redo
        assert not history.is_dirty

    def test_undo_description(self) -> None:
        history = EditHistory()
        recipe = _make_recipe(item_id="Glass")
        history.execute(AddIngredientCommand(recipe, Ingredient("Quartz", 5)))
        assert "Quartz" in history.undo_description
        assert "Glass" in history.undo_description

    def test_redo_description(self) -> None:
        history = EditHistory()
        recipe = _make_recipe(item_id="Glass")
        history.execute(AddIngredientCommand(recipe, Ingredient("Quartz", 5)))
        history.undo()
        assert "Quartz" in history.redo_description

    def test_empty_descriptions(self) -> None:
        history = EditHistory()
        assert history.undo_description == ""
        assert history.redo_description == ""


# ---------------------------------------------------------------------------
# AddIngredientCommand
# ---------------------------------------------------------------------------


class TestAddIngredientCommand:
    """Test adding ingredients to a recipe."""

    def test_execute_appends_ingredient(self) -> None:
        recipe = _make_recipe()
        cmd = AddIngredientCommand(recipe, Ingredient("Titanium", 3))
        cmd.execute()
        assert len(recipe.ingredients) == 1
        assert recipe.ingredients[0].item_id == "Titanium"
        assert recipe.ingredients[0].required == 3

    def test_undo_removes_appended_ingredient(self) -> None:
        recipe = _make_recipe()
        cmd = AddIngredientCommand(recipe, Ingredient("Titanium", 3))
        cmd.execute()
        cmd.undo()
        assert len(recipe.ingredients) == 0

    def test_multiple_adds_then_undo(self) -> None:
        recipe = _make_recipe()
        cmd1 = AddIngredientCommand(recipe, Ingredient("A", 1))
        cmd2 = AddIngredientCommand(recipe, Ingredient("B", 2))
        cmd1.execute()
        cmd2.execute()
        assert len(recipe.ingredients) == 2
        cmd2.undo()
        assert len(recipe.ingredients) == 1
        assert recipe.ingredients[0].item_id == "A"

    def test_description(self) -> None:
        recipe = _make_recipe(item_id="Glass")
        cmd = AddIngredientCommand(recipe, Ingredient("Quartz", 5))
        assert "Quartz" in cmd.description
        assert "Glass" in cmd.description


# ---------------------------------------------------------------------------
# RemoveIngredientCommand
# ---------------------------------------------------------------------------


class TestRemoveIngredientCommand:
    """Test removing ingredients by index."""

    def test_execute_removes_at_index(self) -> None:
        recipe = _make_recipe(
            ingredients=[
                Ingredient("A", 1),
                Ingredient("B", 2),
                Ingredient("C", 3),
            ]
        )
        cmd = RemoveIngredientCommand(recipe, index=1)
        cmd.execute()
        assert len(recipe.ingredients) == 2
        assert recipe.ingredients[0].item_id == "A"
        assert recipe.ingredients[1].item_id == "C"

    def test_undo_restores_at_original_index(self) -> None:
        recipe = _make_recipe(
            ingredients=[
                Ingredient("A", 1),
                Ingredient("B", 2),
                Ingredient("C", 3),
            ]
        )
        cmd = RemoveIngredientCommand(recipe, index=1)
        cmd.execute()
        cmd.undo()
        assert len(recipe.ingredients) == 3
        assert recipe.ingredients[1].item_id == "B"

    def test_remove_first(self) -> None:
        recipe = _make_recipe(
            ingredients=[
                Ingredient("A", 1),
                Ingredient("B", 2),
            ]
        )
        cmd = RemoveIngredientCommand(recipe, index=0)
        cmd.execute()
        assert recipe.ingredients[0].item_id == "B"
        cmd.undo()
        assert recipe.ingredients[0].item_id == "A"

    def test_remove_last(self) -> None:
        recipe = _make_recipe(
            ingredients=[
                Ingredient("A", 1),
                Ingredient("B", 2),
            ]
        )
        cmd = RemoveIngredientCommand(recipe, index=1)
        cmd.execute()
        assert len(recipe.ingredients) == 1
        cmd.undo()
        assert recipe.ingredients[1].item_id == "B"

    def test_description_shows_captured_name(self) -> None:
        recipe = _make_recipe(item_id="Glass", ingredients=[Ingredient("Quartz", 5)])
        cmd = RemoveIngredientCommand(recipe, index=0)
        cmd.execute()
        assert "Quartz" in cmd.description
        assert "Glass" in cmd.description


# ---------------------------------------------------------------------------
# ChangeIngredientCommand
# ---------------------------------------------------------------------------


class TestChangeIngredientCommand:
    """Test swapping a frozen Ingredient at a given index."""

    def test_execute_replaces_ingredient(self) -> None:
        recipe = _make_recipe(ingredients=[Ingredient("A", 1)])
        new_ing = Ingredient("B", 5)
        cmd = ChangeIngredientCommand(recipe, index=0, new_ingredient=new_ing)
        cmd.execute()
        assert recipe.ingredients[0].item_id == "B"
        assert recipe.ingredients[0].required == 5

    def test_undo_restores_original(self) -> None:
        recipe = _make_recipe(ingredients=[Ingredient("A", 1)])
        cmd = ChangeIngredientCommand(recipe, index=0, new_ingredient=Ingredient("B", 5))
        cmd.execute()
        cmd.undo()
        assert recipe.ingredients[0].item_id == "A"
        assert recipe.ingredients[0].required == 1

    def test_change_middle_element(self) -> None:
        recipe = _make_recipe(
            ingredients=[
                Ingredient("A", 1),
                Ingredient("B", 2),
                Ingredient("C", 3),
            ]
        )
        cmd = ChangeIngredientCommand(recipe, index=1, new_ingredient=Ingredient("X", 10))
        cmd.execute()
        assert recipe.ingredients[1].item_id == "X"
        cmd.undo()
        assert recipe.ingredients[1].item_id == "B"

    def test_swaps_ingredient_on_custom_fabricator(self) -> None:
        fab = CustomFabricator(
            item_id="MyFab",
            ingredients=[Ingredient("Titanium", 2)],
        )
        cmd = ChangeIngredientCommand(fab, index=0, new_ingredient=Ingredient("Titanium", 9))
        cmd.execute()
        assert fab.ingredients[0] == Ingredient("Titanium", 9)
        cmd.undo()
        assert fab.ingredients[0] == Ingredient("Titanium", 2)


# ---------------------------------------------------------------------------
# ChangeRecipeFieldCommand
# ---------------------------------------------------------------------------


class TestChangeRecipeFieldCommand:
    """Test changing scalar recipe fields via setattr."""

    def test_change_amount_crafted(self) -> None:
        recipe = _make_recipe()
        cmd = ChangeRecipeFieldCommand(recipe, "amount_crafted", 5)
        cmd.execute()
        assert recipe.amount_crafted == 5

    def test_undo_restores_original_value(self) -> None:
        recipe = _make_recipe()
        recipe.amount_crafted = 3
        cmd = ChangeRecipeFieldCommand(recipe, "amount_crafted", 10)
        cmd.execute()
        cmd.undo()
        assert recipe.amount_crafted == 3

    def test_change_item_id(self) -> None:
        recipe = _make_recipe(item_id="OldName")
        cmd = ChangeRecipeFieldCommand(recipe, "item_id", "NewName")
        cmd.execute()
        assert recipe.item_id == "NewName"
        cmd.undo()
        assert recipe.item_id == "OldName"

    def test_change_force_unlock(self) -> None:
        recipe = _make_recipe()
        assert recipe.force_unlock_at_start is None
        cmd = ChangeRecipeFieldCommand(recipe, "force_unlock_at_start", True)
        cmd.execute()
        assert recipe.force_unlock_at_start is True
        cmd.undo()
        assert recipe.force_unlock_at_start is None

    def test_change_alias_display_name(self) -> None:
        recipe = AliasRecipe(item_id="MyAlias", display_name="Old Name")
        cmd = ChangeRecipeFieldCommand(recipe, "display_name", "New Name")
        cmd.execute()
        assert recipe.display_name == "New Name"
        cmd.undo()
        assert recipe.display_name == "Old Name"

    def test_description(self) -> None:
        recipe = _make_recipe(item_id="Glass")
        cmd = ChangeRecipeFieldCommand(recipe, "amount_crafted", 5)
        assert "amount_crafted" in cmd.description
        assert "Glass" in cmd.description


# ---------------------------------------------------------------------------
# AddRecipeCommand
# ---------------------------------------------------------------------------


class TestAddRecipeCommand:
    """Test adding recipes to the correct ParsedFile list."""

    def test_add_modified_recipe(self) -> None:
        pf = _make_parsed_file()
        recipe = ModifiedRecipe(item_id="NewItem")
        cmd = AddRecipeCommand(pf, recipe)
        cmd.execute()
        assert len(pf.modified_recipes) == 1
        assert pf.modified_recipes[0].item_id == "NewItem"

    def test_undo_removes_added_recipe(self) -> None:
        pf = _make_parsed_file()
        recipe = ModifiedRecipe(item_id="NewItem")
        cmd = AddRecipeCommand(pf, recipe)
        cmd.execute()
        cmd.undo()
        assert len(pf.modified_recipes) == 0

    def test_add_added_recipe_goes_to_correct_list(self) -> None:
        pf = _make_parsed_file(block_type=BlockType.ADDED_RECIPES)
        recipe = AddedRecipe(item_id="NewAdded", path="Fab/Tab")
        cmd = AddRecipeCommand(pf, recipe)
        cmd.execute()
        assert len(pf.added_recipes) == 1
        assert len(pf.modified_recipes) == 0

    def test_add_alias_recipe_goes_to_correct_list(self) -> None:
        pf = _make_parsed_file(block_type=BlockType.ALIAS_RECIPES)
        recipe = AliasRecipe(item_id="NewAlias", display_name="Test")
        cmd = AddRecipeCommand(pf, recipe)
        cmd.execute()
        assert len(pf.alias_recipes) == 1

    def test_add_custom_food_goes_to_correct_list(self) -> None:
        pf = _make_parsed_file(block_type=BlockType.CUSTOM_FOODS)
        recipe = CustomFood(item_id="NewFood", food_value=20)
        cmd = AddRecipeCommand(pf, recipe)
        cmd.execute()
        assert len(pf.custom_foods) == 1

    def test_description(self) -> None:
        pf = _make_parsed_file()
        recipe = ModifiedRecipe(item_id="Glass")
        cmd = AddRecipeCommand(pf, recipe)
        assert "Glass" in cmd.description


# ---------------------------------------------------------------------------
# RemoveRecipeCommand
# ---------------------------------------------------------------------------


class TestRemoveRecipeCommand:
    """Test removing recipes from a ParsedFile."""

    def test_remove_recipe(self) -> None:
        recipe = ModifiedRecipe(item_id="Glass")
        pf = _make_parsed_file([recipe])
        cmd = RemoveRecipeCommand(pf, recipe)
        cmd.execute()
        assert len(pf.modified_recipes) == 0

    def test_undo_restores_recipe(self) -> None:
        recipe = ModifiedRecipe(item_id="Glass")
        pf = _make_parsed_file([recipe])
        cmd = RemoveRecipeCommand(pf, recipe)
        cmd.execute()
        cmd.undo()
        assert len(pf.modified_recipes) == 1
        assert pf.modified_recipes[0].item_id == "Glass"

    def test_undo_preserves_index(self) -> None:
        r1 = ModifiedRecipe(item_id="A")
        r2 = ModifiedRecipe(item_id="B")
        r3 = ModifiedRecipe(item_id="C")
        pf = _make_parsed_file([r1, r2, r3])
        cmd = RemoveRecipeCommand(pf, r2)
        cmd.execute()
        assert len(pf.modified_recipes) == 2
        cmd.undo()
        assert pf.modified_recipes[1].item_id == "B"

    def test_remove_alias_from_correct_list(self) -> None:
        recipe = AliasRecipe(item_id="MyAlias", display_name="Test")
        pf = _make_parsed_file([recipe], block_type=BlockType.ALIAS_RECIPES)
        cmd = RemoveRecipeCommand(pf, recipe)
        cmd.execute()
        assert len(pf.alias_recipes) == 0
        cmd.undo()
        assert len(pf.alias_recipes) == 1

    def test_description(self) -> None:
        recipe = ModifiedRecipe(item_id="Glass")
        pf = _make_parsed_file([recipe])
        cmd = RemoveRecipeCommand(pf, recipe)
        assert "Glass" in cmd.description


# ---------------------------------------------------------------------------
# CompoundCommand
# ---------------------------------------------------------------------------


class TestCompoundCommand:
    """Test grouping multiple commands into one undo step."""

    def test_execute_runs_all(self) -> None:
        recipe = _make_recipe()
        cmd = CompoundCommand(
            commands=[
                AddIngredientCommand(recipe, Ingredient("A", 1)),
                AddIngredientCommand(recipe, Ingredient("B", 2)),
            ],
            _description="Add two ingredients",
        )
        cmd.execute()
        assert len(recipe.ingredients) == 2

    def test_undo_reverses_all(self) -> None:
        recipe = _make_recipe()
        cmd = CompoundCommand(
            commands=[
                AddIngredientCommand(recipe, Ingredient("A", 1)),
                AddIngredientCommand(recipe, Ingredient("B", 2)),
            ],
        )
        cmd.execute()
        cmd.undo()
        assert len(recipe.ingredients) == 0

    def test_undo_reverses_in_order(self) -> None:
        """Undo applies sub-commands in reverse order."""
        recipe = _make_recipe(ingredients=[Ingredient("X", 1)])
        cmd = CompoundCommand(
            commands=[
                AddIngredientCommand(recipe, Ingredient("A", 1)),
                ChangeIngredientCommand(recipe, index=0, new_ingredient=Ingredient("Y", 5)),
            ],
        )
        cmd.execute()
        # After execute: [Y, A] (change index 0 from X to Y, then add A)
        # Wait, execute order: first add A -> [X, A], then change index 0 -> [Y, A]
        assert recipe.ingredients[0].item_id == "Y"
        assert recipe.ingredients[1].item_id == "A"
        cmd.undo()
        # Undo reverses: first undo change (restore X at 0), then undo add (remove A)
        assert len(recipe.ingredients) == 1
        assert recipe.ingredients[0].item_id == "X"

    def test_description(self) -> None:
        cmd = CompoundCommand(commands=[], _description="Edit recipe fields")
        assert cmd.description == "Edit recipe fields"

    def test_default_description(self) -> None:
        cmd = CompoundCommand(commands=[])
        assert cmd.description == "Compound edit"

    def test_compound_in_history(self) -> None:
        """Compound commands work with EditHistory as a single undo step."""
        history = EditHistory()
        recipe = _make_recipe()
        cmd = CompoundCommand(
            commands=[
                AddIngredientCommand(recipe, Ingredient("A", 1)),
                AddIngredientCommand(recipe, Ingredient("B", 2)),
                AddIngredientCommand(recipe, Ingredient("C", 3)),
            ],
        )
        history.execute(cmd)
        assert len(recipe.ingredients) == 3
        history.undo()
        assert len(recipe.ingredients) == 0
        history.redo()
        assert len(recipe.ingredients) == 3


# ---------------------------------------------------------------------------
# Integration: commands -> model state -> verify
# ---------------------------------------------------------------------------


class TestCommandIntegration:
    """Integration tests: apply sequences of commands and verify model state."""

    def test_build_recipe_from_scratch(self) -> None:
        """Create a recipe, add ingredients, change amounts, then undo all."""
        pf = _make_parsed_file()
        history = EditHistory()

        recipe = ModifiedRecipe(item_id="ComputerChip")
        history.execute(AddRecipeCommand(pf, recipe))
        assert len(pf.modified_recipes) == 1

        history.execute(AddIngredientCommand(recipe, Ingredient("Gold", 1)))
        history.execute(AddIngredientCommand(recipe, Ingredient("Copper", 2)))
        assert len(recipe.ingredients) == 2

        history.execute(
            ChangeIngredientCommand(recipe, index=1, new_ingredient=Ingredient("Copper", 4))
        )
        assert recipe.ingredients[1].required == 4

        history.execute(ChangeRecipeFieldCommand(recipe, "amount_crafted", 2))
        assert recipe.amount_crafted == 2

        # Undo everything
        history.undo()  # amount_crafted back to 1
        assert recipe.amount_crafted == 1
        history.undo()  # Copper back to 2
        assert recipe.ingredients[1].required == 2
        history.undo()  # remove Copper
        assert len(recipe.ingredients) == 1
        history.undo()  # remove Gold
        assert len(recipe.ingredients) == 0
        history.undo()  # remove recipe
        assert len(pf.modified_recipes) == 0

    def test_edit_then_save_clears_dirty(self) -> None:
        """Edit, mark saved, verify clean state."""
        history = EditHistory()
        recipe = _make_recipe()
        history.execute(AddIngredientCommand(recipe, Ingredient("A", 1)))
        assert history.is_dirty
        history.mark_saved()
        assert not history.is_dirty

    def test_undo_redo_preserves_data(self) -> None:
        """Multiple undo/redo cycles preserve exact data."""
        recipe = _make_recipe(
            ingredients=[
                Ingredient("A", 1),
                Ingredient("B", 2),
            ]
        )
        history = EditHistory()

        history.execute(RemoveIngredientCommand(recipe, index=0))
        assert recipe.ingredients[0].item_id == "B"

        history.undo()
        assert recipe.ingredients[0].item_id == "A"
        assert recipe.ingredients[1].item_id == "B"

        history.redo()
        assert len(recipe.ingredients) == 1
        assert recipe.ingredients[0].item_id == "B"

        history.undo()
        assert len(recipe.ingredients) == 2

    def test_mixed_recipe_types_in_parsed_file(self) -> None:
        """Add different recipe types and verify they go to correct lists."""
        pf = ParsedFile(source_path=Path("test.txt"), block_type=BlockType.MODIFIED_RECIPES)
        history = EditHistory()

        mod = ModifiedRecipe(item_id="ModItem")
        added = AddedRecipe(item_id="AddedItem")
        alias = AliasRecipe(item_id="AliasItem", display_name="Test")
        food = CustomFood(item_id="FoodItem", food_value=10)

        history.execute(AddRecipeCommand(pf, mod))
        history.execute(AddRecipeCommand(pf, added))
        history.execute(AddRecipeCommand(pf, alias))
        history.execute(AddRecipeCommand(pf, food))

        assert len(pf.modified_recipes) == 1
        assert len(pf.added_recipes) == 1
        assert len(pf.alias_recipes) == 1
        assert len(pf.custom_foods) == 1

        # Undo all
        for _ in range(4):
            history.undo()

        assert len(pf.modified_recipes) == 0
        assert len(pf.added_recipes) == 0
        assert len(pf.alias_recipes) == 0
        assert len(pf.custom_foods) == 0


# ---------------------------------------------------------------------------
# AddNonRecipeCommand
# ---------------------------------------------------------------------------


class TestAddNonRecipeCommand:
    """Test adding non-recipe entries to the correct ParsedFile list."""

    def test_add_custom_fabricator(self) -> None:
        pf = _make_parsed_file()
        fab = CustomFabricator(item_id="MyFab")
        cmd = AddNonRecipeCommand(pf, fab)
        cmd.execute()
        assert len(pf.custom_fabricators) == 1
        assert pf.custom_fabricators[0].item_id == "MyFab"

    def test_add_crafting_tab(self) -> None:
        pf = _make_parsed_file()
        tab = CraftingTab(tab_id="MyTab")
        cmd = AddNonRecipeCommand(pf, tab)
        cmd.execute()
        assert len(pf.crafting_tabs) == 1
        assert pf.crafting_tabs[0].tab_id == "MyTab"

    def test_add_moved_recipe(self) -> None:
        pf = _make_parsed_file()
        mr = MovedRecipe(item_id="Titanium", old_path="Resources", new_path="Custom")
        cmd = AddNonRecipeCommand(pf, mr)
        cmd.execute()
        assert len(pf.moved_recipes) == 1

    def test_add_custom_size(self) -> None:
        pf = _make_parsed_file()
        cs = CustomSize(item_id="Battery", width=2, height=1)
        cmd = AddNonRecipeCommand(pf, cs)
        cmd.execute()
        assert len(pf.custom_sizes) == 1
        assert pf.custom_sizes[0].width == 2

    def test_add_custom_bio_fuel(self) -> None:
        pf = _make_parsed_file()
        bf = CustomBioFuel(item_id="Peeper", energy=200.0)
        cmd = AddNonRecipeCommand(pf, bf)
        cmd.execute()
        assert len(pf.custom_bio_fuels) == 1
        assert pf.custom_bio_fuels[0].energy == 200.0

    def test_add_custom_fragment_count(self) -> None:
        pf = _make_parsed_file()
        fc = CustomFragmentCount(item_id="Cyclops", fragments_to_scan=5)
        cmd = AddNonRecipeCommand(pf, fc)
        cmd.execute()
        assert len(pf.custom_fragment_counts) == 1
        assert pf.custom_fragment_counts[0].fragments_to_scan == 5

    def test_undo_removes_entry(self) -> None:
        pf = _make_parsed_file()
        cs = CustomSize(item_id="Battery", width=2, height=1)
        cmd = AddNonRecipeCommand(pf, cs)
        cmd.execute()
        cmd.undo()
        assert len(pf.custom_sizes) == 0

    def test_description_uses_item_id(self) -> None:
        pf = _make_parsed_file()
        cs = CustomSize(item_id="Battery")
        cmd = AddNonRecipeCommand(pf, cs)
        assert "Battery" in cmd.description

    def test_description_uses_tab_id(self) -> None:
        pf = _make_parsed_file()
        tab = CraftingTab(tab_id="MyTab")
        cmd = AddNonRecipeCommand(pf, tab)
        assert "MyTab" in cmd.description


# ---------------------------------------------------------------------------
# RemoveNonRecipeCommand
# ---------------------------------------------------------------------------


class TestRemoveNonRecipeCommand:
    """Test removing non-recipe entries from a ParsedFile."""

    def test_remove_custom_size(self) -> None:
        pf = _make_parsed_file()
        cs = CustomSize(item_id="Battery", width=2, height=1)
        pf.custom_sizes.append(cs)
        cmd = RemoveNonRecipeCommand(pf, cs)
        cmd.execute()
        assert len(pf.custom_sizes) == 0

    def test_undo_restores_entry(self) -> None:
        pf = _make_parsed_file()
        bf = CustomBioFuel(item_id="Peeper", energy=200.0)
        pf.custom_bio_fuels.append(bf)
        cmd = RemoveNonRecipeCommand(pf, bf)
        cmd.execute()
        cmd.undo()
        assert len(pf.custom_bio_fuels) == 1
        assert pf.custom_bio_fuels[0].item_id == "Peeper"

    def test_undo_preserves_index(self) -> None:
        pf = _make_parsed_file()
        s1 = CustomSize(item_id="A")
        s2 = CustomSize(item_id="B")
        s3 = CustomSize(item_id="C")
        pf.custom_sizes.extend([s1, s2, s3])
        cmd = RemoveNonRecipeCommand(pf, s2)
        cmd.execute()
        assert len(pf.custom_sizes) == 2
        cmd.undo()
        assert pf.custom_sizes[1].item_id == "B"

    def test_remove_crafting_tab(self) -> None:
        pf = _make_parsed_file()
        tab = CraftingTab(tab_id="TestTab", display_name="Test")
        pf.crafting_tabs.append(tab)
        cmd = RemoveNonRecipeCommand(pf, tab)
        cmd.execute()
        assert len(pf.crafting_tabs) == 0
        cmd.undo()
        assert len(pf.crafting_tabs) == 1

    def test_description(self) -> None:
        pf = _make_parsed_file()
        fab = CustomFabricator(item_id="MyFab")
        pf.custom_fabricators.append(fab)
        cmd = RemoveNonRecipeCommand(pf, fab)
        assert "MyFab" in cmd.description


# ---------------------------------------------------------------------------
# Non-recipe command integration
# ---------------------------------------------------------------------------


class TestNonRecipeIntegration:
    """Integration tests for non-recipe commands with EditHistory."""

    def test_all_non_recipe_types_with_history(self) -> None:
        """Add one of each non-recipe type, then undo all."""
        pf = _make_parsed_file()
        history = EditHistory()

        history.execute(AddNonRecipeCommand(pf, CustomFabricator(item_id="Fab1")))
        history.execute(AddNonRecipeCommand(pf, CraftingTab(tab_id="Tab1")))
        history.execute(AddNonRecipeCommand(pf, MovedRecipe(item_id="Moved1")))
        history.execute(AddNonRecipeCommand(pf, CustomSize(item_id="Size1")))
        history.execute(AddNonRecipeCommand(pf, CustomBioFuel(item_id="Fuel1")))
        history.execute(AddNonRecipeCommand(pf, CustomFragmentCount(item_id="Frag1")))

        assert len(pf.custom_fabricators) == 1
        assert len(pf.crafting_tabs) == 1
        assert len(pf.moved_recipes) == 1
        assert len(pf.custom_sizes) == 1
        assert len(pf.custom_bio_fuels) == 1
        assert len(pf.custom_fragment_counts) == 1

        # Undo all
        for _ in range(6):
            history.undo()

        assert len(pf.custom_fabricators) == 0
        assert len(pf.crafting_tabs) == 0
        assert len(pf.moved_recipes) == 0
        assert len(pf.custom_sizes) == 0
        assert len(pf.custom_bio_fuels) == 0
        assert len(pf.custom_fragment_counts) == 0

        # Redo all
        for _ in range(6):
            history.redo()

        assert len(pf.custom_fabricators) == 1
        assert len(pf.crafting_tabs) == 1


class TestChangeNonRecipeFieldCommand:
    """Tests for ChangeNonRecipeFieldCommand."""

    def test_change_custom_size_width(self) -> None:
        entry = CustomSize(item_id="Knife", width=1, height=1)
        cmd = ChangeNonRecipeFieldCommand(entry, "width", 3)
        cmd.execute()
        assert entry.width == 3

    def test_undo_restores_old_value(self) -> None:
        entry = CustomSize(item_id="Knife", width=1, height=2)
        cmd = ChangeNonRecipeFieldCommand(entry, "height", 5)
        cmd.execute()
        assert entry.height == 5
        cmd.undo()
        assert entry.height == 2

    def test_change_biofuel_energy(self) -> None:
        entry = CustomBioFuel(item_id="Creepvine", energy=100.0)
        cmd = ChangeNonRecipeFieldCommand(entry, "energy", 250.0)
        cmd.execute()
        assert entry.energy == 250.0

    def test_change_fragment_count(self) -> None:
        entry = CustomFragmentCount(item_id="Seaglide", fragments_to_scan=3)
        cmd = ChangeNonRecipeFieldCommand(entry, "fragments_to_scan", 5)
        cmd.execute()
        assert entry.fragments_to_scan == 5

    def test_change_crafting_tab_field(self) -> None:
        entry = CraftingTab(tab_id="Weapons", display_name="Weapons")
        cmd = ChangeNonRecipeFieldCommand(entry, "display_name", "Heavy Weapons")
        cmd.execute()
        assert entry.display_name == "Heavy Weapons"
        cmd.undo()
        assert entry.display_name == "Weapons"

    def test_change_moved_recipe_paths(self) -> None:
        entry = MovedRecipe(item_id="Knife", old_path="Fab/A", new_path="Fab/B")
        cmd = ChangeNonRecipeFieldCommand(entry, "new_path", "Fab/C")
        cmd.execute()
        assert entry.new_path == "Fab/C"

    def test_change_moved_recipe_bool(self) -> None:
        entry = MovedRecipe(item_id="Knife")
        cmd = ChangeNonRecipeFieldCommand(entry, "hidden", True)
        cmd.execute()
        assert entry.hidden is True
        cmd.undo()
        assert entry.hidden is False

    def test_description_uses_entry_id(self) -> None:
        entry = CustomSize(item_id="Knife", width=1, height=1)
        cmd = ChangeNonRecipeFieldCommand(entry, "width", 3)
        assert "width" in cmd.description
        assert "Knife" in cmd.description

    def test_description_for_crafting_tab(self) -> None:
        entry = CraftingTab(tab_id="Weapons")
        cmd = ChangeNonRecipeFieldCommand(entry, "display_name", "New Name")
        assert "Weapons" in cmd.description

    def test_with_history(self) -> None:
        entry = CustomSize(item_id="Knife", width=1, height=1)
        history = EditHistory()
        history.execute(ChangeNonRecipeFieldCommand(entry, "width", 4))
        history.execute(ChangeNonRecipeFieldCommand(entry, "height", 3))
        assert entry.width == 4
        assert entry.height == 3
        history.undo()
        assert entry.height == 1
        history.undo()
        assert entry.width == 1


# ---------------------------------------------------------------------------
# NestTabInFabricatorCommand
# ---------------------------------------------------------------------------


class TestNestTabInFabricatorCommand:
    """NestTabInFabricatorCommand: moves a tab from top-level into a fabricator."""

    def test_execute_moves_tab_into_fabricator(self) -> None:
        tab = CraftingTab(tab_id="WeaponsTab")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            crafting_tabs=[tab],
            custom_fabricators=[fab],
        )
        cmd = NestTabInFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab)
        cmd.execute()
        assert tab not in pf.crafting_tabs
        assert tab in fab.tabs
        assert tab.parent_tab_path == "MyFab"

    def test_undo_restores_tab_to_top_level(self) -> None:
        tab = CraftingTab(tab_id="WeaponsTab")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            crafting_tabs=[tab],
            custom_fabricators=[fab],
        )
        cmd = NestTabInFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab)
        cmd.execute()
        cmd.undo()
        assert tab in pf.crafting_tabs
        assert tab not in fab.tabs
        assert tab.parent_tab_path == ""

    def test_execute_when_tab_already_nested_is_noop_safe(self) -> None:
        """If tab is not in top-level list (already nested), execute still adds to fab."""
        tab = CraftingTab(tab_id="WeaponsTab")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        cmd = NestTabInFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab)
        cmd.execute()
        assert tab in fab.tabs
        assert tab.parent_tab_path == "MyFab"

    def test_undo_when_tab_not_in_top_level(self) -> None:
        """Undo when tab was not in top-level only removes from fab.tabs."""
        tab = CraftingTab(tab_id="WeaponsTab")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        cmd = NestTabInFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab)
        cmd.execute()
        cmd.undo()
        assert tab not in fab.tabs
        assert tab not in pf.crafting_tabs  # was never there, stays not there
        assert tab.parent_tab_path == ""


# ---------------------------------------------------------------------------
# NestRecipeInFabricatorCommand
# ---------------------------------------------------------------------------


class TestNestRecipeInFabricatorCommand:
    """NestRecipeInFabricatorCommand: moves a recipe into a fabricator's nested list."""

    def test_execute_moves_added_recipe_into_fabricator(self) -> None:
        recipe = AddedRecipe(item_id="LaserGun")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            added_recipes=[recipe],
            custom_fabricators=[fab],
        )
        cmd = NestRecipeInFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
            path="MyFab",
        )
        cmd.execute()
        assert recipe not in pf.added_recipes
        assert recipe in fab.added_recipes
        assert recipe.path == "MyFab"

    def test_execute_moves_alias_recipe_into_fabricator(self) -> None:
        recipe = AliasRecipe(item_id="QuickKnife")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            alias_recipes=[recipe],
            custom_fabricators=[fab],
        )
        cmd = NestRecipeInFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
            path="MyFab",
        )
        cmd.execute()
        assert recipe not in pf.alias_recipes
        assert recipe in fab.alias_recipes
        assert recipe.path == "MyFab"

    def test_execute_moves_custom_food_into_fabricator(self) -> None:
        recipe = CustomFood(item_id="SuperMeal")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_foods=[recipe],
            custom_fabricators=[fab],
        )
        cmd = NestRecipeInFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
            path="MyFab",
        )
        cmd.execute()
        assert recipe not in pf.custom_foods
        assert recipe in fab.custom_foods
        assert recipe.path == "MyFab"

    def test_undo_restores_recipe_to_top_level(self) -> None:
        recipe = AddedRecipe(item_id="LaserGun")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            added_recipes=[recipe],
            custom_fabricators=[fab],
        )
        cmd = NestRecipeInFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
            path="MyFab",
        )
        cmd.execute()
        cmd.undo()
        assert recipe in pf.added_recipes
        assert recipe not in fab.added_recipes
        assert recipe.path == ""

    def test_description_includes_recipe_and_fab(self) -> None:
        recipe = AddedRecipe(item_id="LaserGun")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        cmd = NestRecipeInFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
            path="MyFab",
        )
        assert "LaserGun" in cmd.description
        assert "MyFab" in cmd.description

    def test_modified_recipe_is_silently_skipped(self) -> None:
        """ModifiedRecipe cannot be nested in a fabricator; execute is a no-op."""
        recipe = ModifiedRecipe(item_id="Titanium")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MODIFIED_RECIPES,
            modified_recipes=[recipe],
            custom_fabricators=[fab],
        )
        cmd = NestRecipeInFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
            path="MyFab",  # type: ignore[arg-type]
        )
        cmd.execute()
        assert recipe in pf.modified_recipes  # not moved
        assert len(fab.added_recipes) == 0
        cmd.undo()  # should be a safe no-op
        assert recipe in pf.modified_recipes


# ---------------------------------------------------------------------------
# UnnestTabFromFabricatorCommand
# ---------------------------------------------------------------------------


class TestUnnestTabFromFabricatorCommand:
    """UnnestTabFromFabricatorCommand: moves a tab from a fabricator back to top-level."""

    def test_execute_moves_tab_to_top_level(self) -> None:
        tab = CraftingTab(tab_id="WeaponsTab", parent_tab_path="MyFab")
        fab = CustomFabricator(item_id="MyFab", tabs=[tab])
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        cmd = UnnestTabFromFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab)
        cmd.execute()
        assert tab not in fab.tabs
        assert tab in pf.crafting_tabs
        assert tab.parent_tab_path == ""

    def test_undo_restores_tab_in_fabricator(self) -> None:
        tab = CraftingTab(tab_id="WeaponsTab", parent_tab_path="MyFab")
        fab = CustomFabricator(item_id="MyFab", tabs=[tab])
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        cmd = UnnestTabFromFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab)
        cmd.execute()
        cmd.undo()
        assert tab in fab.tabs
        assert tab not in pf.crafting_tabs
        assert tab.parent_tab_path == "MyFab"

    def test_undo_preserves_index(self) -> None:
        tab_a = CraftingTab(tab_id="TabA")
        tab_b = CraftingTab(tab_id="TabB", parent_tab_path="MyFab")
        tab_c = CraftingTab(tab_id="TabC")
        fab = CustomFabricator(item_id="MyFab", tabs=[tab_a, tab_b, tab_c])
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        cmd = UnnestTabFromFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab_b)
        cmd.execute()
        assert len(fab.tabs) == 2
        cmd.undo()
        assert fab.tabs[1].tab_id == "TabB"

    def test_description_includes_tab_and_fab(self) -> None:
        tab = CraftingTab(tab_id="WeaponsTab")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
        )
        cmd = UnnestTabFromFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab)
        assert "WeaponsTab" in cmd.description
        assert "MyFab" in cmd.description

    def test_round_trip_with_nest_command(self) -> None:
        """Unnest is the exact reverse of nest: nest then unnest returns to original state."""
        tab = CraftingTab(tab_id="Tools")
        fab = CustomFabricator(item_id="CraftFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            crafting_tabs=[tab],
            custom_fabricators=[fab],
        )
        nest_cmd = NestTabInFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab)
        nest_cmd.execute()
        assert tab in fab.tabs
        assert tab not in pf.crafting_tabs

        unnest_cmd = UnnestTabFromFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab)
        unnest_cmd.execute()
        assert tab not in fab.tabs
        assert tab in pf.crafting_tabs
        assert tab.parent_tab_path == ""

    def test_with_history_undo_redo(self) -> None:
        tab = CraftingTab(tab_id="Gear", parent_tab_path="Fab1")
        fab = CustomFabricator(item_id="Fab1", tabs=[tab])
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        history = EditHistory()
        history.execute(UnnestTabFromFabricatorCommand(parsed_file=pf, fabricator=fab, tab=tab))
        assert tab in pf.crafting_tabs
        assert tab not in fab.tabs

        history.undo()
        assert tab in fab.tabs
        assert tab not in pf.crafting_tabs
        assert tab.parent_tab_path == "Fab1"

        history.redo()
        assert tab in pf.crafting_tabs
        assert tab.parent_tab_path == ""


# ---------------------------------------------------------------------------
# UnnestRecipeFromFabricatorCommand
# ---------------------------------------------------------------------------


class TestUnnestRecipeFromFabricatorCommand:
    """UnnestRecipeFromFabricatorCommand: moves a recipe from a fabricator back to top-level."""

    def test_execute_moves_added_recipe_to_top_level(self) -> None:
        recipe = AddedRecipe(item_id="LaserGun", path="MyFab")
        fab = CustomFabricator(item_id="MyFab", added_recipes=[recipe])
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        cmd = UnnestRecipeFromFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
        )
        cmd.execute()
        assert recipe not in fab.added_recipes
        assert recipe in pf.added_recipes
        assert recipe.path == ""

    def test_execute_moves_alias_recipe_to_top_level(self) -> None:
        recipe = AliasRecipe(item_id="QuickKnife", path="MyFab")
        fab = CustomFabricator(item_id="MyFab", alias_recipes=[recipe])
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        cmd = UnnestRecipeFromFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
        )
        cmd.execute()
        assert recipe not in fab.alias_recipes
        assert recipe in pf.alias_recipes
        assert recipe.path == ""

    def test_execute_moves_custom_food_to_top_level(self) -> None:
        recipe = CustomFood(item_id="SuperMeal", path="MyFab")
        fab = CustomFabricator(item_id="MyFab", custom_foods=[recipe])
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        cmd = UnnestRecipeFromFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
        )
        cmd.execute()
        assert recipe not in fab.custom_foods
        assert recipe in pf.custom_foods
        assert recipe.path == ""

    def test_undo_restores_recipe_in_fabricator(self) -> None:
        recipe = AddedRecipe(item_id="LaserGun", path="MyFab")
        fab = CustomFabricator(item_id="MyFab", added_recipes=[recipe])
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        cmd = UnnestRecipeFromFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
        )
        cmd.execute()
        cmd.undo()
        assert recipe in fab.added_recipes
        assert recipe not in pf.added_recipes
        assert recipe.path == "MyFab"

    def test_undo_preserves_index(self) -> None:
        r1 = AddedRecipe(item_id="A", path="Fab")
        r2 = AddedRecipe(item_id="B", path="Fab")
        r3 = AddedRecipe(item_id="C", path="Fab")
        fab = CustomFabricator(item_id="Fab", added_recipes=[r1, r2, r3])
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        cmd = UnnestRecipeFromFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=r2,
        )
        cmd.execute()
        assert len(fab.added_recipes) == 2
        cmd.undo()
        assert fab.added_recipes[1].item_id == "B"

    def test_description_includes_recipe_and_fab(self) -> None:
        recipe = AddedRecipe(item_id="LaserGun")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
        )
        cmd = UnnestRecipeFromFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
        )
        assert "LaserGun" in cmd.description
        assert "MyFab" in cmd.description

    def test_modified_recipe_is_silently_skipped(self) -> None:
        """ModifiedRecipe cannot be nested/unnested; execute is a no-op."""
        recipe = ModifiedRecipe(item_id="Titanium")
        fab = CustomFabricator(item_id="MyFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MODIFIED_RECIPES,
            custom_fabricators=[fab],
        )
        cmd = UnnestRecipeFromFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,  # type: ignore[arg-type]
        )
        cmd.execute()
        assert len(pf.added_recipes) == 0
        cmd.undo()  # safe no-op

    def test_round_trip_with_nest_command(self) -> None:
        """Unnest is the exact reverse of nest: nest then unnest returns to original state."""
        recipe = AddedRecipe(item_id="PlasmaSword")
        fab = CustomFabricator(item_id="WeaponsFab")
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            added_recipes=[recipe],
            custom_fabricators=[fab],
        )
        nest_cmd = NestRecipeInFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
            path="WeaponsFab",
        )
        nest_cmd.execute()
        assert recipe in fab.added_recipes
        assert recipe not in pf.added_recipes

        unnest_cmd = UnnestRecipeFromFabricatorCommand(
            parsed_file=pf,
            fabricator=fab,
            recipe=recipe,
        )
        unnest_cmd.execute()
        assert recipe not in fab.added_recipes
        assert recipe in pf.added_recipes
        assert recipe.path == ""

    def test_with_history_undo_redo(self) -> None:
        recipe = AddedRecipe(item_id="ThermalBlade", path="CraftFab")
        fab = CustomFabricator(item_id="CraftFab", added_recipes=[recipe])
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        history = EditHistory()
        history.execute(
            UnnestRecipeFromFabricatorCommand(
                parsed_file=pf,
                fabricator=fab,
                recipe=recipe,
            )
        )
        assert recipe in pf.added_recipes
        assert recipe not in fab.added_recipes

        history.undo()
        assert recipe in fab.added_recipes
        assert recipe not in pf.added_recipes
        assert recipe.path == "CraftFab"

        history.redo()
        assert recipe in pf.added_recipes
        assert recipe.path == ""
