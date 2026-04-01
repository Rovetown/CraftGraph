"""Tests for the CraftGraph data model.

Verifies construction, defaults, inheritance, and the ParsedFile.all_recipes
aggregation property for all 10 CC3 block types.
"""

from pathlib import Path

from craftgraph.models import (
    CRAFT_TREE_TYPES,
    SN1_CRAFT_TREE_PATH_ROOTS,
    AddedRecipe,
    AliasRecipe,
    BlockType,
    CraftTreeEntry,
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
# Ingredient (frozen value object)
# ---------------------------------------------------------------------------


class TestIngredient:
    def test_construction(self) -> None:
        ing = Ingredient(item_id="Titanium", required=2)
        assert ing.item_id == "Titanium"
        assert ing.required == 2

    def test_frozen(self) -> None:
        ing = Ingredient(item_id="Titanium", required=2)
        try:
            ing.item_id = "Gold"  # type: ignore[misc]
            raise AssertionError("Expected FrozenInstanceError")
        except AttributeError:
            pass

    def test_equality(self) -> None:
        a = Ingredient(item_id="Titanium", required=2)
        b = Ingredient(item_id="Titanium", required=2)
        assert a == b

    def test_inequality(self) -> None:
        a = Ingredient(item_id="Titanium", required=2)
        b = Ingredient(item_id="Gold", required=1)
        assert a != b

    def test_hashable(self) -> None:
        """Frozen dataclasses are hashable -- useful for sets and dict keys."""
        ing = Ingredient(item_id="Titanium", required=2)
        assert hash(ing) == hash(Ingredient(item_id="Titanium", required=2))
        assert {ing} == {Ingredient(item_id="Titanium", required=2)}


# ---------------------------------------------------------------------------
# Recipe hierarchy
# ---------------------------------------------------------------------------


class TestModifiedRecipe:
    def test_defaults(self) -> None:
        recipe = ModifiedRecipe(item_id="Knife")
        assert recipe.item_id == "Knife"
        assert recipe.amount_crafted == 1
        assert recipe.ingredients == []
        assert recipe.linked_item_ids == []
        assert recipe.unlocks == []
        assert recipe.force_unlock_at_start is None
        assert recipe.unlocked_by == []

    def test_with_ingredients(self) -> None:
        recipe = ModifiedRecipe(
            item_id="Knife",
            amount_crafted=1,
            ingredients=[
                Ingredient(item_id="Titanium", required=1),
                Ingredient(item_id="Silicone", required=1),
            ],
        )
        assert len(recipe.ingredients) == 2
        assert recipe.ingredients[0].item_id == "Titanium"

    def test_with_linked_items(self) -> None:
        recipe = ModifiedRecipe(
            item_id="Battery",
            linked_item_ids=["AcidMushroom", "CopperOre"],
        )
        assert recipe.linked_item_ids == ["AcidMushroom", "CopperOre"]


class TestAddedRecipe:
    def test_inherits_modified_recipe(self) -> None:
        recipe = AddedRecipe(item_id="BigFilteredWater", path="Fabricator/Water")
        assert isinstance(recipe, ModifiedRecipe)
        assert recipe.item_id == "BigFilteredWater"
        assert recipe.path == "Fabricator/Water"

    def test_added_defaults(self) -> None:
        recipe = AddedRecipe(item_id="X")
        assert recipe.path == ""
        assert recipe.pda_group is None
        assert recipe.pda_category is None
        # inherited defaults
        assert recipe.amount_crafted == 1
        assert recipe.ingredients == []


class TestAliasRecipe:
    def test_inherits_added_recipe(self) -> None:
        recipe = AliasRecipe(
            item_id="SodiumBicarbonate",
            display_name="Sodium Bicarbonate",
            tooltip="Baking soda, essentially.",
        )
        assert isinstance(recipe, AddedRecipe)
        assert isinstance(recipe, ModifiedRecipe)
        assert recipe.display_name == "Sodium Bicarbonate"
        assert recipe.tooltip == "Baking soda, essentially."

    def test_alias_defaults(self) -> None:
        recipe = AliasRecipe(item_id="X")
        assert recipe.display_name == ""
        assert recipe.tooltip == ""
        assert recipe.functional_id is None
        assert recipe.sprite_item_id is None


class TestCustomFood:
    def test_inherits_alias_recipe(self) -> None:
        food = CustomFood(
            item_id="CookedPeeper",
            display_name="Cooked Peeper",
            food_value=32,
            water_value=-3,
        )
        assert isinstance(food, AliasRecipe)
        assert isinstance(food, AddedRecipe)
        assert isinstance(food, ModifiedRecipe)
        assert food.food_value == 32
        assert food.water_value == -3

    def test_food_defaults(self) -> None:
        food = CustomFood(item_id="X")
        assert food.food_value == 0
        assert food.water_value == 0
        assert food.oxygen_value == 0
        assert food.health_value == 0
        assert food.decay_rate_mod == 0.0
        assert food.food_type is None
        assert food.use_drink_sound is None


# ---------------------------------------------------------------------------
# Non-recipe entry types
# ---------------------------------------------------------------------------


class TestCraftingTab:
    def test_construction(self) -> None:
        tab = CraftingTab(
            tab_id="AlchFabTab",
            display_name="Alchemy Fab",
            sprite_item_id="LabTrashcan",
            parent_tab_path="Root",
        )
        assert tab.tab_id == "AlchFabTab"
        assert tab.display_name == "Alchemy Fab"
        assert tab.sprite_item_id == "LabTrashcan"
        assert tab.parent_tab_path == "Root"

    def test_defaults(self) -> None:
        tab = CraftingTab(tab_id="MyTab")
        assert tab.display_name == ""
        assert tab.sprite_item_id is None
        assert tab.parent_tab_path == ""


class TestMovedRecipe:
    def test_construction(self) -> None:
        moved = MovedRecipe(
            item_id="Titanium",
            old_path="Resources/BasicMaterials",
            new_path="Resources/AdvancedMaterials",
        )
        assert moved.item_id == "Titanium"
        assert moved.old_path == "Resources/BasicMaterials"
        assert moved.new_path == "Resources/AdvancedMaterials"

    def test_hidden(self) -> None:
        moved = MovedRecipe(item_id="Titanium", hidden=True)
        assert moved.hidden is True
        assert moved.copied is False

    def test_defaults(self) -> None:
        moved = MovedRecipe(item_id="X")
        assert moved.old_path is None
        assert moved.new_path is None
        assert moved.copied is False
        assert moved.hidden is False


class TestCustomFabricator:
    def test_construction_with_nested(self) -> None:
        fab = CustomFabricator(
            item_id="AlchFab",
            display_name="Alchemy Fabricator",
            tooltip="A custom fabricator.",
            model="Fabricator",
            color_tint=[0.5, 0.5, 1.0, 1.0],
            tabs=[CraftingTab(tab_id="TabA", display_name="Tab A")],
            added_recipes=[AddedRecipe(item_id="ItemA", path="TabA")],
            alias_recipes=[AliasRecipe(item_id="AliasA", display_name="Alias A")],
        )
        assert fab.item_id == "AlchFab"
        assert len(fab.tabs) == 1
        assert len(fab.added_recipes) == 1
        assert len(fab.alias_recipes) == 1

    def test_defaults(self) -> None:
        fab = CustomFabricator(item_id="X")
        assert fab.display_name == ""
        assert fab.tooltip == ""
        assert fab.model == "Fabricator"
        assert fab.color_tint == []
        assert fab.allowed_in_base is True
        assert fab.allowed_in_cyclops is True
        assert fab.ingredients == []
        assert fab.pda_group is None
        assert fab.pda_category is None
        assert fab.force_unlock_at_start is None
        assert fab.unlocked_by == []
        assert fab.tabs == []
        assert fab.added_recipes == []
        assert fab.alias_recipes == []
        assert fab.moved_recipes == []
        assert fab.custom_foods == []


class TestCustomSize:
    def test_construction(self) -> None:
        size = CustomSize(item_id="BigTank", width=2, height=3)
        assert size.item_id == "BigTank"
        assert size.width == 2
        assert size.height == 3

    def test_defaults(self) -> None:
        size = CustomSize(item_id="X")
        assert size.width == 1
        assert size.height == 1


class TestCustomBioFuel:
    def test_construction(self) -> None:
        fuel = CustomBioFuel(item_id="CreepvinePiece", energy=157.5)
        assert fuel.item_id == "CreepvinePiece"
        assert fuel.energy == 157.5

    def test_defaults(self) -> None:
        fuel = CustomBioFuel(item_id="X")
        assert fuel.energy == 0.0


class TestCustomFragmentCount:
    def test_construction(self) -> None:
        frag = CustomFragmentCount(item_id="SeamothFragment", fragments_to_scan=3)
        assert frag.item_id == "SeamothFragment"
        assert frag.fragments_to_scan == 3

    def test_defaults(self) -> None:
        frag = CustomFragmentCount(item_id="X")
        assert frag.fragments_to_scan == 1


# ---------------------------------------------------------------------------
# CraftTree.Type entries
# ---------------------------------------------------------------------------


class TestCraftTreeTypes:
    def test_centrifuge_marked_below_zero_only(self) -> None:
        centrifuge = next(ct for ct in CRAFT_TREE_TYPES if ct.value == "Centrifuge")
        assert centrifuge.below_zero_only is True

    def test_centrifuge_excluded_from_sn1_roots(self) -> None:
        assert "Centrifuge" not in SN1_CRAFT_TREE_PATH_ROOTS

    def test_sn1_roots_include_all_non_bz_types(self) -> None:
        expected = {ct.tree_root for ct in CRAFT_TREE_TYPES if not ct.below_zero_only}
        assert SN1_CRAFT_TREE_PATH_ROOTS == expected

    def test_sn1_roots_contain_known_stations(self) -> None:
        for root in ("Fabricator", "Workbench", "CyclopsFabricator",
                     "SeamothUpgrades", "MapRoomFunctionality", "Constructor", "Rocket"):
            assert root in SN1_CRAFT_TREE_PATH_ROOTS

    def test_craft_tree_entry_frozen(self) -> None:
        entry = CraftTreeEntry("Test", "Test Label", "Test")
        try:
            entry.value = "Other"  # type: ignore[misc]
            raise AssertionError("Expected FrozenInstanceError")
        except AttributeError:
            pass


# ---------------------------------------------------------------------------
# BlockType enum
# ---------------------------------------------------------------------------


class TestBlockType:
    def test_all_ten_types(self) -> None:
        assert len(BlockType) == 10

    def test_values_match_cc3_keywords(self) -> None:
        assert BlockType.MODIFIED_RECIPES.value == "ModifiedRecipes"
        assert BlockType.ADDED_RECIPES.value == "AddedRecipes"
        assert BlockType.ALIAS_RECIPES.value == "AliasRecipes"
        assert BlockType.CUSTOM_CRAFTING_TABS.value == "CustomCraftingTabs"
        assert BlockType.CUSTOM_FABRICATORS.value == "CustomFabricators"
        assert BlockType.MOVED_RECIPES.value == "MovedRecipes"
        assert BlockType.CUSTOM_SIZES.value == "CustomSizes"
        assert BlockType.CUSTOM_BIO_FUELS.value == "CustomBioFuels"
        assert BlockType.CUSTOM_FRAGMENT_COUNTS.value == "CustomFragmentCounts"
        assert BlockType.CUSTOM_FOODS.value == "CustomFoods"

    def test_lookup_by_value(self) -> None:
        assert BlockType("AddedRecipes") is BlockType.ADDED_RECIPES


# ---------------------------------------------------------------------------
# ParsedFile container
# ---------------------------------------------------------------------------


class TestParsedFile:
    def test_empty_file(self) -> None:
        pf = ParsedFile(source_path=Path("test.txt"))
        assert pf.block_type is None
        assert pf.all_recipes == []

    def test_all_recipes_flat(self) -> None:
        """all_recipes collects from modified, added, alias, and custom_foods."""
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MODIFIED_RECIPES,
            modified_recipes=[ModifiedRecipe(item_id="M1")],
            added_recipes=[AddedRecipe(item_id="A1")],
            alias_recipes=[AliasRecipe(item_id="Al1")],
            custom_foods=[CustomFood(item_id="F1")],
        )
        ids = [r.item_id for r in pf.all_recipes]
        assert ids == ["M1", "A1", "Al1", "F1"]

    def test_all_recipes_includes_fabricator_nested(self) -> None:
        """all_recipes also traverses recipes nested inside custom fabricators."""
        fab = CustomFabricator(
            item_id="MyFab",
            added_recipes=[AddedRecipe(item_id="FabAdded")],
            alias_recipes=[AliasRecipe(item_id="FabAlias")],
            custom_foods=[CustomFood(item_id="FabFood")],
        )
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        ids = [r.item_id for r in pf.all_recipes]
        assert "FabAdded" in ids
        assert "FabAlias" in ids
        assert "FabFood" in ids

    def test_all_recipes_combined(self) -> None:
        """all_recipes combines top-level and fabricator-nested recipes."""
        fab = CustomFabricator(
            item_id="Fab",
            added_recipes=[AddedRecipe(item_id="Nested")],
        )
        pf = ParsedFile(
            source_path=Path("test.txt"),
            modified_recipes=[ModifiedRecipe(item_id="TopLevel")],
            custom_fabricators=[fab],
        )
        ids = [r.item_id for r in pf.all_recipes]
        assert ids == ["TopLevel", "Nested"]

    def test_list_independence(self) -> None:
        """Each ParsedFile instance gets its own list instances."""
        pf1 = ParsedFile(source_path=Path("a.txt"))
        pf2 = ParsedFile(source_path=Path("b.txt"))
        pf1.modified_recipes.append(ModifiedRecipe(item_id="X"))
        assert len(pf2.modified_recipes) == 0
