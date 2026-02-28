"""Tests for the EasyMarkup serializer (inverse of parser).

Covers:
  - escape_value / quote_string helpers
  - Per-type entry serialization (all 10 block types)
  - Default omission (fields at their default are not emitted)
  - Full ParsedFile serialization via serialize_file()
  - Round-trip fidelity: parse -> serialize -> parse == identity
  - Integration round-trips against real CC3 reference files
"""

from pathlib import Path

import pytest

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
from craftgraph.parser import clean_value, parse_file, unescape_value
from craftgraph.serializer import (
    escape_value,
    quote_string,
    serialize_file,
)

# ---------------------------------------------------------------------------
# Reference file paths
# ---------------------------------------------------------------------------

_REF_DIR = Path(__file__).resolve().parent.parent / "craftgraph" / "cc3_reference_files"
_REAL_MOD_EXAMPLES = _REF_DIR / "real-mod-examples"
_SAMPLE_FILES = _REF_DIR / "original-source" / "CustomCraft3" / "SampleFiles"


def _roundtrip(parsed: ParsedFile, tmp_path: Path) -> ParsedFile:
    """Serialize a ParsedFile, write to disk, re-parse, and return the result."""
    text = serialize_file(parsed)
    out = tmp_path / "roundtrip.txt"
    out.write_text(text, encoding="utf-8")
    return parse_file(out)


# ---------------------------------------------------------------------------
# TestEscapeValue
# ---------------------------------------------------------------------------


class TestEscapeValue:
    """Test the escape_value() helper."""

    def test_plain_string_unchanged(self) -> None:
        assert escape_value("Titanium") == "Titanium"

    def test_empty_string(self) -> None:
        assert escape_value("") == ""

    def test_colon_escaped(self) -> None:
        assert escape_value("a:b") == "a\\:b"

    def test_semicolon_escaped(self) -> None:
        assert escape_value("a;b") == "a\\;b"

    def test_paren_escaped(self) -> None:
        assert escape_value("a(b)c") == "a\\(b\\)c"

    def test_comma_escaped(self) -> None:
        assert escape_value("a,b") == "a\\,b"

    def test_hash_escaped(self) -> None:
        assert escape_value("a#b") == "a\\#b"

    def test_backslash_escaped(self) -> None:
        assert escape_value("a\\b") == "a\\\\b"

    def test_quote_escaped(self) -> None:
        assert escape_value('a"b') == 'a\\"b'

    def test_multiple_specials(self) -> None:
        assert escape_value("a:b;c") == "a\\:b\\;c"

    def test_spaces_wrapped_in_quotes(self) -> None:
        """Values with spaces are wrapped in quotes (CC3 strategy)."""
        assert escape_value("a b") == '"a b"'

    def test_spaces_with_special_chars_wrapped(self) -> None:
        """Spaces win over per-char escaping -- entire value is quoted."""
        assert escape_value("a:b c") == '"a:b c"'

    def test_no_spaces_still_escapes(self) -> None:
        """Without spaces, individual chars are still backslash-escaped."""
        assert escape_value("a:b") == "a\\:b"

    def test_spaces_value_roundtrip(self) -> None:
        """A value with spaces and special chars survives serialize->parse."""
        original = "hello:world (test)"
        escaped = escape_value(original)
        assert escaped == '"hello:world (test)"'
        restored = unescape_value(clean_value(escaped))
        assert restored == original


# ---------------------------------------------------------------------------
# TestQuoteString
# ---------------------------------------------------------------------------


class TestQuoteString:
    """Test the quote_string() helper."""

    def test_simple_string(self) -> None:
        assert quote_string("Hello World") == '"Hello World"'

    def test_empty_string(self) -> None:
        assert quote_string("") == '""'

    def test_string_with_special_chars(self) -> None:
        assert quote_string("Use this: item") == '"Use this: item"'


# ---------------------------------------------------------------------------
# TestSerializeModifiedRecipe
# ---------------------------------------------------------------------------


class TestSerializeModifiedRecipe:
    """Test serialization of ModifiedRecipe entries."""

    def test_minimal_recipe(self, tmp_path: Path) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MODIFIED_RECIPES,
            modified_recipes=[ModifiedRecipe(item_id="Titanium")],
        )
        text = serialize_file(pf)
        assert "ModifiedRecipes:" in text
        assert "ItemID: Titanium;" in text

    def test_recipe_with_ingredients(self, tmp_path: Path) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MODIFIED_RECIPES,
            modified_recipes=[
                ModifiedRecipe(
                    item_id="EnameledGlass",
                    amount_crafted=2,
                    ingredients=[
                        Ingredient("Glass", 1),
                        Ingredient("Diamond", 3),
                    ],
                ),
            ],
        )
        text = serialize_file(pf)
        assert "AmountCrafted: 2;" in text
        assert "Ingredients:" in text
        assert "( ItemID: Glass; Required: 1; )," in text
        assert "( ItemID: Diamond; Required: 3; );" in text

    def test_recipe_with_all_fields(self, tmp_path: Path) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MODIFIED_RECIPES,
            modified_recipes=[
                ModifiedRecipe(
                    item_id="Knife",
                    amount_crafted=1,
                    ingredients=[Ingredient("Titanium", 2)],
                    linked_item_ids=["KnifeBlade", "KnifeHandle"],
                    unlocks=["AdvancedKnife"],
                    force_unlock_at_start=False,
                    unlocked_by=["BasicTools"],
                ),
            ],
        )
        text = serialize_file(pf)
        assert "LinkedItemIDs: KnifeBlade, KnifeHandle;" in text
        assert "Unlocks: AdvancedKnife;" in text
        assert "ForceUnlockAtStart: NO;" in text
        assert "UnlockedBy: BasicTools;" in text

    def test_multiple_recipes_comma_semicolon(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MODIFIED_RECIPES,
            modified_recipes=[
                ModifiedRecipe(item_id="A"),
                ModifiedRecipe(item_id="B"),
            ],
        )
        text = serialize_file(pf)
        # First entry ends with ),  second with );
        lines = text.split("\n")
        close_lines = [ln.strip() for ln in lines if ln.strip().startswith(")")]
        assert close_lines[0] == "),"
        assert close_lines[1] == ");"


# ---------------------------------------------------------------------------
# TestSerializeAddedRecipe
# ---------------------------------------------------------------------------


class TestSerializeAddedRecipe:
    """Test serialization of AddedRecipe entries."""

    def test_added_recipe_with_path(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.ADDED_RECIPES,
            added_recipes=[
                AddedRecipe(
                    item_id="bigfilteredwater",
                    ingredients=[Ingredient("bleach", 1)],
                    path="Fabricator/Survival/Water",
                    unlocked_by=["disinfectedwater"],
                    force_unlock_at_start=False,
                ),
            ],
        )
        text = serialize_file(pf)
        assert "AddedRecipes:" in text
        assert "Path: Fabricator/Survival/Water;" in text
        assert "UnlockedBy: disinfectedwater;" in text

    def test_added_recipe_with_pda_fields(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.ADDED_RECIPES,
            added_recipes=[
                AddedRecipe(
                    item_id="TestItem",
                    pda_group="Resources",
                    pda_category="BasicMaterials",
                ),
            ],
        )
        text = serialize_file(pf)
        assert "PdaGroup: Resources;" in text
        assert "PdaCategory: BasicMaterials;" in text


# ---------------------------------------------------------------------------
# TestSerializeAliasRecipe
# ---------------------------------------------------------------------------


class TestSerializeAliasRecipe:
    """Test serialization of AliasRecipe entries."""

    def test_alias_recipe_with_display(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.ALIAS_RECIPES,
            alias_recipes=[
                AliasRecipe(
                    item_id="Alch_Lab",
                    display_name="Alchemic Lab",
                    tooltip="A fancy lab for alchemy",
                    functional_id="LabEquipment",
                    sprite_item_id="Titanium",
                    path="Alch_Fab/Alch_Lab",
                    force_unlock_at_start=False,
                ),
            ],
        )
        text = serialize_file(pf)
        assert "AliasRecipes:" in text
        assert 'DisplayName: "Alchemic Lab";' in text
        assert 'Tooltip: "A fancy lab for alchemy";' in text
        assert "FunctionalID: LabEquipment;" in text
        assert "SpriteItemID: Titanium;" in text
        assert "Path: Alch_Fab/Alch_Lab;" in text


# ---------------------------------------------------------------------------
# TestSerializeCustomFood
# ---------------------------------------------------------------------------


class TestSerializeCustomFood:
    """Test serialization of CustomFood entries."""

    def test_custom_food_with_nutrition(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FOODS,
            custom_foods=[
                CustomFood(
                    item_id="SuperFish",
                    display_name="Super Fish",
                    food_value=50,
                    water_value=20,
                    decay_rate_mod=1.5,
                ),
            ],
        )
        text = serialize_file(pf)
        assert "CustomFoods:" in text
        assert "FoodValue: 50;" in text
        assert "WaterValue: 20;" in text
        assert "DecayRateMod: 1.5;" in text

    def test_custom_food_zero_values_omitted(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FOODS,
            custom_foods=[
                CustomFood(
                    item_id="PlainFood",
                    display_name="Plain",
                    food_value=10,
                ),
            ],
        )
        text = serialize_file(pf)
        assert "FoodValue: 10;" in text
        assert "WaterValue" not in text
        assert "OxygenValue" not in text
        assert "HealthValue" not in text
        assert "DecayRateMod" not in text


# ---------------------------------------------------------------------------
# TestSerializeCraftingTab
# ---------------------------------------------------------------------------


class TestSerializeCraftingTab:
    """Test serialization of CraftingTab entries."""

    def test_crafting_tab(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_CRAFTING_TABS,
            crafting_tabs=[
                CraftingTab(
                    tab_id="Alch_Enzymes",
                    display_name="Complex Enzymes",
                    parent_tab_path="Alch_Fab/Alch_ComplexCompounds",
                ),
            ],
        )
        text = serialize_file(pf)
        assert "CustomCraftingTabs:" in text
        assert "TabID: Alch_Enzymes;" in text
        assert 'DisplayName: "Complex Enzymes";' in text
        assert "ParentTabPath: Alch_Fab/Alch_ComplexCompounds;" in text


# ---------------------------------------------------------------------------
# TestSerializeMovedRecipe
# ---------------------------------------------------------------------------


class TestSerializeMovedRecipe:
    """Test serialization of MovedRecipe entries."""

    def test_moved_recipe_with_paths(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MOVED_RECIPES,
            moved_recipes=[
                MovedRecipe(
                    item_id="Knife",
                    old_path="Fabricator/Personal/Tools",
                    new_path="Fabricator/Personal/Equipment",
                    copied=True,
                    hidden=False,
                ),
            ],
        )
        text = serialize_file(pf)
        assert "MovedRecipes:" in text
        assert "OldPath: Fabricator/Personal/Tools;" in text
        assert "NewPath: Fabricator/Personal/Equipment;" in text
        assert "Copied: YES;" in text
        assert "Hidden" not in text  # False is default, omitted

    def test_moved_recipe_hidden(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MOVED_RECIPES,
            moved_recipes=[
                MovedRecipe(item_id="OldItem", hidden=True),
            ],
        )
        text = serialize_file(pf)
        assert "Hidden: YES;" in text


# ---------------------------------------------------------------------------
# TestSerializeCustomSize
# ---------------------------------------------------------------------------


class TestSerializeCustomSize:
    """Test serialization of CustomSize entries."""

    def test_custom_size(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_SIZES,
            custom_sizes=[
                CustomSize(item_id="seat", width=1, height=2),
                CustomSize(item_id="hulk", width=3, height=3),
            ],
        )
        text = serialize_file(pf)
        assert "CustomSizes:" in text
        assert "ItemID: seat;" in text
        assert "Width: 1;" in text
        assert "Height: 2;" in text
        assert "ItemID: hulk;" in text

    def test_custom_size_always_writes_dimensions(self) -> None:
        """Width and Height are always written, even at defaults."""
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_SIZES,
            custom_sizes=[CustomSize(item_id="tiny", width=1, height=1)],
        )
        text = serialize_file(pf)
        assert "Width: 1;" in text
        assert "Height: 1;" in text


# ---------------------------------------------------------------------------
# TestSerializeCustomBioFuel
# ---------------------------------------------------------------------------


class TestSerializeCustomBioFuel:
    """Test serialization of CustomBioFuel entries."""

    def test_custom_bio_fuel(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_BIO_FUELS,
            custom_bio_fuels=[
                CustomBioFuel(item_id="OrganicMatter", energy=500.0),
            ],
        )
        text = serialize_file(pf)
        assert "CustomBioFuels:" in text
        assert "Energy: 500;" in text


# ---------------------------------------------------------------------------
# TestSerializeCustomFragmentCount
# ---------------------------------------------------------------------------


class TestSerializeCustomFragmentCount:
    """Test serialization of CustomFragmentCount entries."""

    def test_custom_fragment_count(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FRAGMENT_COUNTS,
            custom_fragment_counts=[
                CustomFragmentCount(item_id="CyclopsHullFragment", fragments_to_scan=5),
            ],
        )
        text = serialize_file(pf)
        assert "CustomFragmentCounts:" in text
        assert "FragmentsToScan: 5;" in text

    def test_default_fragments_omitted(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FRAGMENT_COUNTS,
            custom_fragment_counts=[
                CustomFragmentCount(item_id="BasicFragment"),
            ],
        )
        text = serialize_file(pf)
        assert "FragmentsToScan" not in text


# ---------------------------------------------------------------------------
# TestSerializeCustomFabricator
# ---------------------------------------------------------------------------


class TestSerializeCustomFabricator:
    """Test serialization of CustomFabricator entries (complex nested type)."""

    def test_fabricator_with_tabs(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[
                CustomFabricator(
                    item_id="MyFab",
                    display_name="My Fabricator",
                    tooltip="A custom fabricator",
                    model="MoonPool",
                    color_tint=[0.1, 1.0, 0.5, 1.0],
                    tabs=[
                        CraftingTab(tab_id="Tab1", display_name="First Tab"),
                        CraftingTab(
                            tab_id="Tab2",
                            display_name="Second Tab",
                            parent_tab_path="MyFab/Tab1",
                        ),
                    ],
                ),
            ],
        )
        text = serialize_file(pf)
        assert "CustomFabricators:" in text
        assert 'DisplayName: "My Fabricator";' in text
        assert 'Tooltip: "A custom fabricator";' in text
        assert "Model: MoonPool;" in text
        assert "ColorTint: 0.1, 1, 0.5, 1;" in text
        assert "CustomCraftingTabs:" in text
        assert "TabID: Tab1;" in text
        assert "TabID: Tab2;" in text

    def test_fabricator_with_nested_recipes(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[
                CustomFabricator(
                    item_id="TestFab",
                    alias_recipes=[
                        AliasRecipe(
                            item_id="AliasA",
                            display_name="Alias A",
                            path="TestFab/Tab1",
                        ),
                    ],
                    added_recipes=[
                        AddedRecipe(
                            item_id="AddedA",
                            path="TestFab/Tab1",
                            ingredients=[Ingredient("Titanium", 2)],
                        ),
                    ],
                ),
            ],
        )
        text = serialize_file(pf)
        assert "AddedRecipes:" in text
        assert "AliasRecipes:" in text
        assert "ItemID: AliasA;" in text
        assert "ItemID: AddedA;" in text

    def test_fabricator_default_model_omitted(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[
                CustomFabricator(item_id="DefaultFab"),
            ],
        )
        text = serialize_file(pf)
        assert "Model:" not in text

    def test_fabricator_non_default_booleans(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[
                CustomFabricator(
                    item_id="RestrictedFab",
                    allowed_in_base=False,
                    allowed_in_cyclops=False,
                ),
            ],
        )
        text = serialize_file(pf)
        assert "AllowedInBase: NO;" in text
        assert "AllowedInCyclops: NO;" in text


# ---------------------------------------------------------------------------
# TestDefaultOmission
# ---------------------------------------------------------------------------


class TestDefaultOmission:
    """Verify that default-valued fields are omitted from output."""

    def test_amount_crafted_1_omitted(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MODIFIED_RECIPES,
            modified_recipes=[ModifiedRecipe(item_id="X", amount_crafted=1)],
        )
        text = serialize_file(pf)
        assert "AmountCrafted" not in text

    def test_empty_ingredients_omitted(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MODIFIED_RECIPES,
            modified_recipes=[ModifiedRecipe(item_id="X")],
        )
        text = serialize_file(pf)
        assert "Ingredients" not in text

    def test_none_force_unlock_omitted(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MODIFIED_RECIPES,
            modified_recipes=[ModifiedRecipe(item_id="X")],
        )
        text = serialize_file(pf)
        assert "ForceUnlockAtStart" not in text

    def test_empty_path_omitted(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.ADDED_RECIPES,
            added_recipes=[AddedRecipe(item_id="X")],
        )
        text = serialize_file(pf)
        assert "Path:" not in text

    def test_none_pda_group_omitted(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.ADDED_RECIPES,
            added_recipes=[AddedRecipe(item_id="X")],
        )
        text = serialize_file(pf)
        assert "PdaGroup" not in text

    def test_empty_display_name_omitted(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.ALIAS_RECIPES,
            alias_recipes=[AliasRecipe(item_id="X")],
        )
        text = serialize_file(pf)
        assert "DisplayName" not in text

    def test_fabricator_defaults_omitted(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[CustomFabricator(item_id="X")],
        )
        text = serialize_file(pf)
        assert "Model:" not in text
        assert "ColorTint" not in text
        assert "AllowedInBase" not in text
        assert "AllowedInCyclops" not in text


# ---------------------------------------------------------------------------
# TestSerializeFile
# ---------------------------------------------------------------------------


class TestSerializeFile:
    """Test the top-level serialize_file() function."""

    def test_empty_parsed_file(self) -> None:
        pf = ParsedFile(source_path=Path("empty.txt"))
        assert serialize_file(pf) == ""

    def test_no_entries(self) -> None:
        pf = ParsedFile(source_path=Path("empty.txt"), block_type=BlockType.MODIFIED_RECIPES)
        assert serialize_file(pf) == ""

    def test_block_type_header(self) -> None:
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_SIZES,
            custom_sizes=[CustomSize(item_id="X")],
        )
        text = serialize_file(pf)
        assert text.startswith("CustomSizes:\n")

    def test_all_10_block_types_serialize(self) -> None:
        """Every block type can produce non-empty output."""
        configs: list[ParsedFile] = [
            ParsedFile(
                source_path=Path("t.txt"),
                block_type=BlockType.MODIFIED_RECIPES,
                modified_recipes=[ModifiedRecipe(item_id="X")],
            ),
            ParsedFile(
                source_path=Path("t.txt"),
                block_type=BlockType.ADDED_RECIPES,
                added_recipes=[AddedRecipe(item_id="X")],
            ),
            ParsedFile(
                source_path=Path("t.txt"),
                block_type=BlockType.ALIAS_RECIPES,
                alias_recipes=[AliasRecipe(item_id="X")],
            ),
            ParsedFile(
                source_path=Path("t.txt"),
                block_type=BlockType.CUSTOM_FOODS,
                custom_foods=[CustomFood(item_id="X")],
            ),
            ParsedFile(
                source_path=Path("t.txt"),
                block_type=BlockType.CUSTOM_CRAFTING_TABS,
                crafting_tabs=[CraftingTab(tab_id="X")],
            ),
            ParsedFile(
                source_path=Path("t.txt"),
                block_type=BlockType.CUSTOM_FABRICATORS,
                custom_fabricators=[CustomFabricator(item_id="X")],
            ),
            ParsedFile(
                source_path=Path("t.txt"),
                block_type=BlockType.MOVED_RECIPES,
                moved_recipes=[MovedRecipe(item_id="X")],
            ),
            ParsedFile(
                source_path=Path("t.txt"),
                block_type=BlockType.CUSTOM_SIZES,
                custom_sizes=[CustomSize(item_id="X")],
            ),
            ParsedFile(
                source_path=Path("t.txt"),
                block_type=BlockType.CUSTOM_BIO_FUELS,
                custom_bio_fuels=[CustomBioFuel(item_id="X")],
            ),
            ParsedFile(
                source_path=Path("t.txt"),
                block_type=BlockType.CUSTOM_FRAGMENT_COUNTS,
                custom_fragment_counts=[CustomFragmentCount(item_id="X")],
            ),
        ]
        for pf in configs:
            text = serialize_file(pf)
            assert text, f"Block type {pf.block_type} produced empty output"
            assert pf.block_type is not None
            assert text.startswith(pf.block_type.value + ":\n")


# ---------------------------------------------------------------------------
# TestRoundTripSynthetic
# ---------------------------------------------------------------------------


class TestRoundTripSynthetic:
    """Round-trip tests using synthetic (hand-built) data models."""

    def test_modified_recipe_roundtrip(self, tmp_path: Path) -> None:
        original = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MODIFIED_RECIPES,
            modified_recipes=[
                ModifiedRecipe(
                    item_id="Titanium",
                    amount_crafted=4,
                    ingredients=[
                        Ingredient("ScrapMetal", 2),
                        Ingredient("CopperWire", 1),
                    ],
                    linked_item_ids=["TitaniumIngot"],
                    force_unlock_at_start=False,
                ),
            ],
        )
        rt = _roundtrip(original, tmp_path)
        assert len(rt.modified_recipes) == 1
        recipe = rt.modified_recipes[0]
        assert recipe.item_id == "Titanium"
        assert recipe.amount_crafted == 4
        assert len(recipe.ingredients) == 2
        assert recipe.ingredients[0] == Ingredient("ScrapMetal", 2)
        assert recipe.ingredients[1] == Ingredient("CopperWire", 1)
        assert recipe.linked_item_ids == ["TitaniumIngot"]
        assert recipe.force_unlock_at_start is False

    def test_added_recipe_roundtrip(self, tmp_path: Path) -> None:
        original = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.ADDED_RECIPES,
            added_recipes=[
                AddedRecipe(
                    item_id="BigWater",
                    ingredients=[Ingredient("bleach", 1)],
                    path="Fabricator/Survival/Water",
                    unlocked_by=["disinfectedwater"],
                    force_unlock_at_start=False,
                ),
            ],
        )
        rt = _roundtrip(original, tmp_path)
        assert len(rt.added_recipes) == 1
        recipe = rt.added_recipes[0]
        assert recipe.item_id == "BigWater"
        assert recipe.path == "Fabricator/Survival/Water"
        assert recipe.unlocked_by == ["disinfectedwater"]

    def test_alias_recipe_roundtrip(self, tmp_path: Path) -> None:
        original = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.ALIAS_RECIPES,
            alias_recipes=[
                AliasRecipe(
                    item_id="MyAlias",
                    display_name="My Custom Item",
                    tooltip="A really cool item",
                    functional_id="BaseItem",
                    sprite_item_id="Titanium",
                    path="Fabricator/Resources",
                    pda_group="Resources",
                    pda_category="BasicMaterials",
                    force_unlock_at_start=True,
                    ingredients=[Ingredient("Gold", 2)],
                    linked_item_ids=["BaseItem"],
                ),
            ],
        )
        rt = _roundtrip(original, tmp_path)
        assert len(rt.alias_recipes) == 1
        recipe = rt.alias_recipes[0]
        assert recipe.item_id == "MyAlias"
        assert recipe.display_name == "My Custom Item"
        assert recipe.tooltip == "A really cool item"
        assert recipe.functional_id == "BaseItem"
        assert recipe.sprite_item_id == "Titanium"
        assert recipe.path == "Fabricator/Resources"
        assert recipe.pda_group == "Resources"
        assert recipe.pda_category == "BasicMaterials"
        assert recipe.force_unlock_at_start is True

    def test_custom_food_roundtrip(self, tmp_path: Path) -> None:
        original = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FOODS,
            custom_foods=[
                CustomFood(
                    item_id="SuperFish",
                    display_name="Super Fish",
                    tooltip="Tasty!",
                    food_value=50,
                    water_value=20,
                    health_value=10,
                    decay_rate_mod=1.5,
                    food_type="Cooked",
                    use_drink_sound=False,
                ),
            ],
        )
        rt = _roundtrip(original, tmp_path)
        assert len(rt.custom_foods) == 1
        food = rt.custom_foods[0]
        assert food.item_id == "SuperFish"
        assert food.food_value == 50
        assert food.water_value == 20
        assert food.health_value == 10
        assert food.decay_rate_mod == 1.5
        assert food.food_type == "Cooked"
        assert food.use_drink_sound is False

    def test_crafting_tab_roundtrip(self, tmp_path: Path) -> None:
        original = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_CRAFTING_TABS,
            crafting_tabs=[
                CraftingTab(
                    tab_id="MyTab",
                    display_name="My Tab",
                    sprite_item_id="Titanium",
                    parent_tab_path="Fabricator/Resources",
                ),
            ],
        )
        rt = _roundtrip(original, tmp_path)
        assert len(rt.crafting_tabs) == 1
        tab = rt.crafting_tabs[0]
        assert tab.tab_id == "MyTab"
        assert tab.display_name == "My Tab"
        assert tab.sprite_item_id == "Titanium"
        assert tab.parent_tab_path == "Fabricator/Resources"

    def test_moved_recipe_roundtrip(self, tmp_path: Path) -> None:
        original = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MOVED_RECIPES,
            moved_recipes=[
                MovedRecipe(
                    item_id="Knife",
                    old_path="Fabricator/Personal/Tools",
                    new_path="Fabricator/Personal/Equipment",
                    copied=True,
                    hidden=True,
                ),
            ],
        )
        rt = _roundtrip(original, tmp_path)
        assert len(rt.moved_recipes) == 1
        moved = rt.moved_recipes[0]
        assert moved.item_id == "Knife"
        assert moved.old_path == "Fabricator/Personal/Tools"
        assert moved.new_path == "Fabricator/Personal/Equipment"
        assert moved.copied is True
        assert moved.hidden is True

    def test_custom_size_roundtrip(self, tmp_path: Path) -> None:
        original = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_SIZES,
            custom_sizes=[
                CustomSize(item_id="seat", width=1, height=2),
                CustomSize(item_id="hulk", width=3, height=3),
            ],
        )
        rt = _roundtrip(original, tmp_path)
        assert len(rt.custom_sizes) == 2
        assert rt.custom_sizes[0].item_id == "seat"
        assert rt.custom_sizes[0].width == 1
        assert rt.custom_sizes[0].height == 2
        assert rt.custom_sizes[1].item_id == "hulk"

    def test_custom_bio_fuel_roundtrip(self, tmp_path: Path) -> None:
        original = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_BIO_FUELS,
            custom_bio_fuels=[
                CustomBioFuel(item_id="OrganicMatter", energy=500.0),
            ],
        )
        rt = _roundtrip(original, tmp_path)
        assert len(rt.custom_bio_fuels) == 1
        assert rt.custom_bio_fuels[0].energy == 500.0

    def test_custom_fragment_count_roundtrip(self, tmp_path: Path) -> None:
        original = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FRAGMENT_COUNTS,
            custom_fragment_counts=[
                CustomFragmentCount(item_id="CyclopsHull", fragments_to_scan=5),
            ],
        )
        rt = _roundtrip(original, tmp_path)
        assert len(rt.custom_fragment_counts) == 1
        assert rt.custom_fragment_counts[0].fragments_to_scan == 5

    def test_fabricator_roundtrip(self, tmp_path: Path) -> None:
        original = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[
                CustomFabricator(
                    item_id="TestFab",
                    display_name="Test Fabricator",
                    tooltip="Build stuff",
                    model="MoonPool",
                    color_tint=[0.1, 1.0, 0.5, 1.0],
                    allowed_in_base=True,
                    allowed_in_cyclops=False,
                    ingredients=[Ingredient("AdvancedWiringKit", 1)],
                    pda_group="InteriorModules",
                    pda_category="InteriorModule",
                    force_unlock_at_start=False,
                    unlocked_by=["FarmingTray"],
                    tabs=[
                        CraftingTab(tab_id="Tab1", display_name="First Tab"),
                        CraftingTab(
                            tab_id="Tab2",
                            display_name="Second Tab",
                            parent_tab_path="TestFab/Tab1",
                        ),
                    ],
                    alias_recipes=[
                        AliasRecipe(
                            item_id="AliasA",
                            display_name="Alias Recipe A",
                            tooltip="Make alias A",
                            path="TestFab/Tab1",
                            ingredients=[Ingredient("Titanium", 2)],
                        ),
                    ],
                ),
            ],
        )
        rt = _roundtrip(original, tmp_path)
        assert len(rt.custom_fabricators) == 1
        fab = rt.custom_fabricators[0]
        assert fab.item_id == "TestFab"
        assert fab.display_name == "Test Fabricator"
        assert fab.model == "MoonPool"
        assert fab.color_tint == [0.1, 1.0, 0.5, 1.0]
        assert fab.allowed_in_cyclops is False
        assert len(fab.tabs) == 2
        assert fab.tabs[0].tab_id == "Tab1"
        assert fab.tabs[1].parent_tab_path == "TestFab/Tab1"
        assert len(fab.alias_recipes) == 1
        assert fab.alias_recipes[0].item_id == "AliasA"

    def test_multiple_recipes_roundtrip(self, tmp_path: Path) -> None:
        original = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MODIFIED_RECIPES,
            modified_recipes=[
                ModifiedRecipe(
                    item_id="ItemA",
                    ingredients=[Ingredient("Raw1", 3)],
                ),
                ModifiedRecipe(
                    item_id="ItemB",
                    amount_crafted=2,
                    ingredients=[
                        Ingredient("Raw1", 1),
                        Ingredient("Raw2", 5),
                    ],
                ),
                ModifiedRecipe(item_id="ItemC"),
            ],
        )
        rt = _roundtrip(original, tmp_path)
        assert len(rt.modified_recipes) == 3
        assert rt.modified_recipes[0].item_id == "ItemA"
        assert rt.modified_recipes[1].amount_crafted == 2
        assert len(rt.modified_recipes[1].ingredients) == 2
        assert rt.modified_recipes[2].item_id == "ItemC"


# ---------------------------------------------------------------------------
# TestRoundTripRealFiles -- integration tests against reference files
# ---------------------------------------------------------------------------


class TestRoundTripRealFiles:
    """Parse real CC3 reference files, serialize, re-parse, and verify equality."""

    def test_big_filtered_water_roundtrip(self, tmp_path: Path) -> None:
        """Round-trip BigFilteredWater.txt (1 AddedRecipe)."""
        ref_file = _REAL_MOD_EXAMPLES / "BigFilteredWater.txt"
        if not ref_file.exists():
            pytest.skip(f"Reference file missing: {ref_file}")

        original = parse_file(ref_file)
        rt = _roundtrip(original, tmp_path)

        assert rt.block_type is BlockType.ADDED_RECIPES
        assert len(rt.added_recipes) == 1
        orig = original.added_recipes[0]
        rted = rt.added_recipes[0]
        assert rted.item_id == orig.item_id
        assert rted.ingredients == orig.ingredients
        assert rted.path == orig.path
        assert rted.unlocked_by == orig.unlocked_by
        assert rted.force_unlock_at_start == orig.force_unlock_at_start

    def test_alch_custom_fab_roundtrip(self, tmp_path: Path) -> None:
        """Round-trip __Alch_NEW_CustomFAB__.txt (CustomFabricator with tabs)."""
        ref_file = _REAL_MOD_EXAMPLES / "__Alch_NEW_CustomFAB__.txt"
        if not ref_file.exists():
            pytest.skip(f"Reference file missing: {ref_file}")

        original = parse_file(ref_file)
        rt = _roundtrip(original, tmp_path)

        assert rt.block_type is BlockType.CUSTOM_FABRICATORS
        assert len(rt.custom_fabricators) == len(original.custom_fabricators)

        orig_fab = original.custom_fabricators[0]
        rt_fab = rt.custom_fabricators[0]
        assert rt_fab.item_id == orig_fab.item_id
        assert rt_fab.display_name == orig_fab.display_name
        assert len(rt_fab.tabs) == len(orig_fab.tabs)
        # Verify tab IDs match
        for orig_tab, rt_tab in zip(orig_fab.tabs, rt_fab.tabs, strict=True):
            assert rt_tab.tab_id == orig_tab.tab_id
            assert rt_tab.display_name == orig_tab.display_name

    def test_customfab3_roundtrip(self, tmp_path: Path) -> None:
        """Round-trip customfab3.txt (CustomFabricator with 17 AliasRecipes)."""
        ref_file = _REAL_MOD_EXAMPLES / "customfab3.txt"
        if not ref_file.exists():
            pytest.skip(f"Reference file missing: {ref_file}")

        original = parse_file(ref_file)
        rt = _roundtrip(original, tmp_path)

        assert rt.block_type is BlockType.CUSTOM_FABRICATORS
        orig_fab = original.custom_fabricators[0]
        rt_fab = rt.custom_fabricators[0]
        assert len(rt_fab.alias_recipes) == len(orig_fab.alias_recipes)
        for orig_r, rt_r in zip(orig_fab.alias_recipes, rt_fab.alias_recipes, strict=True):
            assert rt_r.item_id == orig_r.item_id
            assert rt_r.display_name == orig_r.display_name
            assert rt_r.ingredients == orig_r.ingredients

    def test_custom_sizes_roundtrip(self, tmp_path: Path) -> None:
        """Round-trip customsizze.txt (17 CustomSizes)."""
        ref_file = _REAL_MOD_EXAMPLES / "customsizze.txt"
        if not ref_file.exists():
            pytest.skip(f"Reference file missing: {ref_file}")

        original = parse_file(ref_file)
        rt = _roundtrip(original, tmp_path)

        assert rt.block_type is BlockType.CUSTOM_SIZES
        assert len(rt.custom_sizes) == len(original.custom_sizes)
        for orig_s, rt_s in zip(original.custom_sizes, rt.custom_sizes, strict=True):
            assert rt_s.item_id == orig_s.item_id
            assert rt_s.width == orig_s.width
            assert rt_s.height == orig_s.height

    @pytest.mark.parametrize(
        ("filename", "block_type", "attr", "count"),
        [
            ("ModifiedRecipes_Samples.txt", BlockType.MODIFIED_RECIPES, "modified_recipes", 4),
            ("AddedRecipes_Samples.txt", BlockType.ADDED_RECIPES, "added_recipes", 1),
            ("AliasRecipes_Samples.txt", BlockType.ALIAS_RECIPES, "alias_recipes", 2),
            ("CustomFabricator_Sample.txt", BlockType.CUSTOM_FABRICATORS, "custom_fabricators", 1),
            ("CustomTab_Samples.txt", BlockType.CUSTOM_CRAFTING_TABS, "crafting_tabs", 5),
            ("MovedRecipes_Samples2.txt", BlockType.MOVED_RECIPES, "moved_recipes", 4),
            ("CustomSizes_Samples.txt", BlockType.CUSTOM_SIZES, "custom_sizes", 2),
            ("CustomBioFuels_Samples.txt", BlockType.CUSTOM_BIO_FUELS, "custom_bio_fuels", 3),
            (
                "CustomFragments_Samples2.txt",
                BlockType.CUSTOM_FRAGMENT_COUNTS,
                "custom_fragment_counts",
                3,
            ),
            ("CustomFoods_Samplefile.txt", BlockType.CUSTOM_FOODS, "custom_foods", 1),
        ],
        ids=[
            "modified-recipes",
            "added-recipes",
            "alias-recipes",
            "custom-fabricator",
            "crafting-tabs",
            "moved-recipes",
            "custom-sizes",
            "bio-fuels",
            "fragment-counts",
            "custom-foods",
        ],
    )
    def test_sample_file_roundtrip(
        self,
        tmp_path: Path,
        filename: str,
        block_type: BlockType,
        attr: str,
        count: int,
    ) -> None:
        """Round-trip official CC3 SampleFiles (all 10 block types)."""
        ref_file = _SAMPLE_FILES / filename
        if not ref_file.exists():
            pytest.skip(f"Sample file missing: {ref_file}")

        original = parse_file(ref_file)
        rt = _roundtrip(original, tmp_path)

        assert rt.block_type is block_type
        orig_entries = getattr(original, attr)
        rt_entries = getattr(rt, attr)
        assert len(rt_entries) == count

        for orig_e, rt_e in zip(orig_entries, rt_entries, strict=True):
            if hasattr(orig_e, "item_id"):
                assert rt_e.item_id == orig_e.item_id
            elif hasattr(orig_e, "tab_id"):
                assert rt_e.tab_id == orig_e.tab_id


# ---------------------------------------------------------------------------
# TestLineEndings -- line_ending parameter for CC3 PrettyPrint() parity
# ---------------------------------------------------------------------------


class TestLineEndings:
    """Verify the ``line_ending`` parameter on ``serialize_file()``."""

    @staticmethod
    def _simple_parsed_file() -> ParsedFile:
        """Build a minimal ParsedFile with a couple of recipes for testing."""
        return ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.MODIFIED_RECIPES,
            modified_recipes=[
                ModifiedRecipe(
                    item_id="Titanium",
                    amount_crafted=4,
                    ingredients=[Ingredient("ScrapMetal", 1)],
                ),
                ModifiedRecipe(item_id="Glass", ingredients=[Ingredient("Quartz", 2)]),
            ],
        )

    def test_default_uses_lf(self) -> None:
        """Default serialization uses LF (``\\n``), never ``\\r\\n``."""
        pf = self._simple_parsed_file()
        text = serialize_file(pf)
        assert "\n" in text
        assert "\r\n" not in text

    def test_crlf_option(self) -> None:
        """Passing ``line_ending="\\r\\n"`` converts all newlines to CRLF."""
        pf = self._simple_parsed_file()
        text = serialize_file(pf, line_ending="\r\n")
        assert "\r\n" in text
        # Every newline should be CRLF -- stripping \r should recover pure LF text.
        lf_text = serialize_file(pf)
        assert text.replace("\r\n", "\n") == lf_text

    def test_crlf_roundtrip(self, tmp_path: Path) -> None:
        """Serialize with CRLF, write to disk, re-parse, verify data identity."""
        pf = self._simple_parsed_file()
        crlf_text = serialize_file(pf, line_ending="\r\n")

        out = tmp_path / "crlf_test.txt"
        out.write_bytes(crlf_text.encode("utf-8"))

        rt = parse_file(out)
        assert rt.block_type is BlockType.MODIFIED_RECIPES
        assert len(rt.modified_recipes) == 2
        assert rt.modified_recipes[0].item_id == "Titanium"
        assert rt.modified_recipes[0].amount_crafted == 4
        assert rt.modified_recipes[0].ingredients == [Ingredient("ScrapMetal", 1)]
        assert rt.modified_recipes[1].item_id == "Glass"
        assert rt.modified_recipes[1].ingredients == [Ingredient("Quartz", 2)]


# ---------------------------------------------------------------------------
# TestFabricatorInternalOrder -- CC3 processing order within fabricators
# ---------------------------------------------------------------------------


class TestFabricatorInternalOrder:
    """Verify fabricator serialization emits blocks in CC3 processing order."""

    def test_tabs_before_recipes(self) -> None:
        """CustomCraftingTabs must appear before AddedRecipes in output."""
        fab = CustomFabricator(
            item_id="TestFab",
            tabs=[CraftingTab(tab_id="TabA")],
            added_recipes=[AddedRecipe(item_id="RecipeA", path="TestFab/TabA")],
        )
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        output = serialize_file(pf)
        tab_pos = output.index("CustomCraftingTabs:")
        recipe_pos = output.index("AddedRecipes:")
        assert tab_pos < recipe_pos, "Tabs must be serialized before recipes"

    def test_full_cc3_order(self) -> None:
        """All nested block types appear in CC3 processing order."""
        fab = CustomFabricator(
            item_id="OrderFab",
            tabs=[CraftingTab(tab_id="T1")],
            added_recipes=[AddedRecipe(item_id="A1", path="OrderFab")],
            alias_recipes=[
                AliasRecipe(
                    item_id="Al1",
                    display_name="Alias",
                    tooltip="tip",
                    path="OrderFab",
                ),
            ],
            moved_recipes=[
                MovedRecipe(
                    item_id="M1",
                    old_path="Fabricator/Resources",
                    new_path="OrderFab",
                ),
            ],
            custom_foods=[
                CustomFood(
                    item_id="F1",
                    display_name="Food",
                    tooltip="tip",
                    food_value=10,
                    path="OrderFab",
                ),
            ],
        )
        pf = ParsedFile(
            source_path=Path("test.txt"),
            block_type=BlockType.CUSTOM_FABRICATORS,
            custom_fabricators=[fab],
        )
        output = serialize_file(pf)
        positions = [
            output.index("CustomCraftingTabs:"),
            output.index("AddedRecipes:"),
            output.index("AliasRecipes:"),
            output.index("MovedRecipes:"),
            output.index("CustomFoods:"),
        ]
        assert positions == sorted(positions), f"Blocks not in CC3 order: {positions}"
