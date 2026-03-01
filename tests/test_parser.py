"""Tests for the CustomCraft3 EasyMarkup parser.

Step 2a: Low-level tokenizer tests covering comment stripping, escape sequences,
quoted strings, and whitespace normalization.

Step 2b: Block-level parser tests covering block type extraction, entry parsing,
nested collections, comma-separated values, case-insensitive keys, and realistic
snippets from CC3 reference files.

Step 2c: Entry mapping tests verifying that EntryBlock objects are correctly
converted to typed data model instances (ModifiedRecipe, AddedRecipe,
CustomFabricator, etc.).
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
from craftgraph.parser import (
    EntryBlock,
    MappingError,
    ParseError,
    clean_value,
    map_added_recipe,
    map_alias_recipe,
    map_crafting_tab,
    map_custom_bio_fuel,
    map_custom_fabricator,
    map_custom_food,
    map_custom_fragment_count,
    map_custom_size,
    map_modified_recipe,
    map_moved_recipe,
    parse_blocks,
    parse_directory,
    parse_file,
    parse_text,
    resolve_block_type,
    unescape_value,
    validate_parsed_file,
)
from craftgraph.serializer import serialize_file

# ---------------------------------------------------------------------------
# clean_value -- whitespace stripping
# ---------------------------------------------------------------------------


class TestCleanValueWhitespace:
    """CleanValue strips ALL whitespace outside quotes and escapes."""

    def test_no_whitespace(self) -> None:
        assert clean_value("Key:Value;") == "Key:Value;"

    def test_strips_spaces(self) -> None:
        assert clean_value("Key : Value ;") == "Key:Value;"

    def test_strips_leading_trailing(self) -> None:
        assert clean_value("  Key : Value ;  ") == "Key:Value;"

    def test_strips_tabs(self) -> None:
        assert clean_value("\tKey\t:\tValue\t;") == "Key:Value;"

    def test_strips_crlf(self) -> None:
        assert clean_value("Key:\r\nValue\r\n;") == "Key:Value;"

    def test_strips_mixed_whitespace(self) -> None:
        assert clean_value(" \t Key \r\n : \t Value \r\n ; ") == "Key:Value;"

    def test_empty_string(self) -> None:
        assert clean_value("") == ""

    def test_only_whitespace(self) -> None:
        assert clean_value("   \t\r\n  ") == ""

    def test_consecutive_spaces_all_stripped(self) -> None:
        """C# TrimStart removes ALL consecutive spaces greedily."""
        assert clean_value("Key :    Value    ;") == "Key:Value;"


# ---------------------------------------------------------------------------
# clean_value -- comment stripping
# ---------------------------------------------------------------------------


class TestCleanValueComments:
    """Comments are # ... # paired block delimiters, NOT line comments."""

    def test_inline_comment(self) -> None:
        assert clean_value("Key:# a comment #Value;") == "Key:Value;"

    def test_comment_at_start(self) -> None:
        assert clean_value("# header comment #Key:Value;") == "Key:Value;"

    def test_comment_at_end(self) -> None:
        assert clean_value("Key:Value;# trailing #") == "Key:Value;"

    def test_comment_with_whitespace(self) -> None:
        assert clean_value("Key : # comment # Value ;") == "Key:Value;"

    def test_multiple_comments(self) -> None:
        assert clean_value("# c1 #Key:# c2 #Value# c3 #;") == "Key:Value;"

    def test_comment_containing_special_chars(self) -> None:
        """Special chars inside comments are discarded."""
        assert clean_value("Key:# : ; ( ) , #Value;") == "Key:Value;"

    def test_unclosed_comment_eats_rest(self) -> None:
        """An unclosed # consumes all remaining input."""
        assert clean_value("Key:#everything gone") == "Key:"

    def test_empty_comment(self) -> None:
        assert clean_value("Key:##Value;") == "Key:Value;"

    def test_comment_with_newlines(self) -> None:
        result = clean_value("Key:# multi\nline\ncomment #Value;")
        assert result == "Key:Value;"


# ---------------------------------------------------------------------------
# clean_value -- escape sequences
# ---------------------------------------------------------------------------


class TestCleanValueEscapes:
    """Escape sequences: \\ + next char both pass through clean_value."""

    def test_escaped_colon(self) -> None:
        assert clean_value(r"Key:Test\:Value;") == r"Key:Test\:Value;"

    def test_escaped_semicolon(self) -> None:
        assert clean_value(r"Key:Test\;Value;") == r"Key:Test\;Value;"

    def test_escaped_comma(self) -> None:
        assert clean_value(r"Key:Test\,Value;") == r"Key:Test\,Value;"

    def test_escaped_hash(self) -> None:
        assert clean_value(r"Key:Test\#Value;") == r"Key:Test\#Value;"

    def test_escaped_backslash(self) -> None:
        assert clean_value(r"Key:Test\\Value;") == r"Key:Test\\Value;"

    def test_escaped_paren(self) -> None:
        assert clean_value(r"Key:Test\(Value\);") == r"Key:Test\(Value\);"

    def test_escape_preserves_following_space(self) -> None:
        r"""\ followed by space: the space is preserved (not stripped)."""
        assert clean_value("Key:Test\\ Value;") == "Key:Test\\ Value;"

    def test_escape_with_surrounding_whitespace(self) -> None:
        r"""Whitespace around escape pairs is stripped, but escaped char stays."""
        assert clean_value(r" Key : Test\:Value ; ") == r"Key:Test\:Value;"

    def test_escape_at_end(self) -> None:
        r"""Trailing \ with nothing after: just the backslash passes through."""
        assert clean_value("Key:Test\\") == "Key:Test\\"

    def test_multiple_escapes(self) -> None:
        assert clean_value(r"Key:A\:B\;C\,D;") == r"Key:A\:B\;C\,D;"


# ---------------------------------------------------------------------------
# clean_value -- quoted strings
# ---------------------------------------------------------------------------


class TestCleanValueQuotes:
    """Quoted strings preserve their contents verbatim (including whitespace)."""

    def test_quoted_value(self) -> None:
        assert clean_value('Key:"Test Value";') == 'Key:"Test Value";'

    def test_quoted_preserves_spaces(self) -> None:
        assert clean_value('Key : "Test  Value" ;') == 'Key:"Test  Value";'

    def test_quoted_preserves_special_chars(self) -> None:
        assert clean_value('Key:"a:b;c,d(e)f";') == 'Key:"a:b;c,d(e)f";'

    def test_quoted_preserves_hash(self) -> None:
        """# inside quotes is NOT a comment delimiter."""
        assert clean_value('Key:"value # with hash";') == 'Key:"value # with hash";'

    def test_empty_quoted_string(self) -> None:
        assert clean_value('Key:"";') == 'Key:"";'

    def test_multiple_quoted_segments(self) -> None:
        result = clean_value('Key:"hello" "world";')
        assert result == 'Key:"hello""world";'

    def test_unclosed_quote_eats_rest(self) -> None:
        """An unclosed " consumes all remaining input."""
        assert clean_value('Key:"never closed') == 'Key:"never closed'

    def test_quoted_with_newlines(self) -> None:
        """Newlines inside quotes are preserved."""
        assert clean_value('Key:"line1\nline2";') == 'Key:"line1\nline2";'


# ---------------------------------------------------------------------------
# clean_value -- combined behaviors
# ---------------------------------------------------------------------------


class TestCleanValueCombined:
    """Tests mixing comments, escapes, quotes, and whitespace."""

    def test_comment_then_quoted(self) -> None:
        result = clean_value('Key:# comment #"Quoted Value";')
        assert result == 'Key:"Quoted Value";'

    def test_escape_inside_comment_is_discarded(self) -> None:
        r"""Escape inside a comment is just discarded along with the comment."""
        assert clean_value(r"Key:# \: #Value;") == "Key:Value;"

    def test_realistic_recipe_line(self) -> None:
        raw = "  ItemID : Titanium ;  # base material #"
        assert clean_value(raw) == "ItemID:Titanium;"

    def test_realistic_multiline_block(self) -> None:
        raw = "ModifiedRecipes:\r\n(\r\n    ItemID: Titanium;\r\n    AmountCrafted: 1;\r\n)"
        assert clean_value(raw) == "ModifiedRecipes:(ItemID:Titanium;AmountCrafted:1;)"

    def test_realistic_ingredient_block(self) -> None:
        raw = (
            "Ingredients:\r\n"
            "    (\r\n"
            "        ItemID: Gold;\r\n"
            "        Required: 2;\r\n"
            "    ),\r\n"
            "    (\r\n"
            "        ItemID: Silver;\r\n"
            "        Required: 1;\r\n"
            "    );\r\n"
        )
        expected = "Ingredients:(ItemID:Gold;Required:2;),(ItemID:Silver;Required:1;);"
        assert clean_value(raw) == expected

    def test_escaped_hash_not_treated_as_comment(self) -> None:
        r"""When # is escaped, it should NOT start a comment."""
        assert clean_value(r"Key:Value\#More;") == r"Key:Value\#More;"


# ---------------------------------------------------------------------------
# unescape_value -- Phase 2 value extraction
# ---------------------------------------------------------------------------


class TestUnescapeValue:
    """unescape_value resolves escape sequences and strips quote delimiters."""

    def test_plain_value(self) -> None:
        assert unescape_value("TestValue") == "TestValue"

    def test_empty_value(self) -> None:
        assert unescape_value("") == ""

    def test_escaped_colon(self) -> None:
        assert unescape_value(r"Test\:Value") == "Test:Value"

    def test_escaped_semicolon(self) -> None:
        assert unescape_value(r"Test\;Value") == "Test;Value"

    def test_escaped_comma(self) -> None:
        assert unescape_value(r"Test\,Value") == "Test,Value"

    def test_escaped_hash(self) -> None:
        assert unescape_value(r"Test\#Value") == "Test#Value"

    def test_escaped_backslash(self) -> None:
        assert unescape_value(r"Test\\Value") == "Test\\Value"

    def test_escaped_parens(self) -> None:
        assert unescape_value(r"Test\(Value\)") == "Test(Value)"

    def test_quoted_value(self) -> None:
        assert unescape_value('"Test Value"') == "Test Value"

    def test_quoted_special_chars(self) -> None:
        assert unescape_value('"a:b;c,d"') == "a:b;c,d"

    def test_quoted_preserves_internal_spaces(self) -> None:
        assert unescape_value('"Test:  Value"') == "Test:  Value"

    def test_multiple_escapes(self) -> None:
        assert unescape_value(r"A\:B\;C\,D") == "A:B;C,D"

    def test_trailing_backslash(self) -> None:
        """A trailing \\ with nothing after: the backslash itself is kept."""
        assert unescape_value("Test\\") == "Test\\"

    def test_combined_from_cc3_tests(self) -> None:
        """Matches CC3 EasyMarkupTests test cases for list values."""
        assert unescape_value(r"1\:") == "1:"
        assert unescape_value(r"2\,") == "2,"
        assert unescape_value(r"3\;") == "3;"
        assert unescape_value('"4 "') == "4 "
        assert unescape_value('" 5"') == " 5"


# ===========================================================================
# Step 2b: Block-level parser tests
# ===========================================================================


# ---------------------------------------------------------------------------
# parse_blocks -- block type extraction
# ---------------------------------------------------------------------------


class TestParseBlocksBlockType:
    """The block type keyword is extracted from the text before the first ':'."""

    def test_modified_recipes(self) -> None:
        cleaned = "ModifiedRecipes:(ItemID:Titanium;)"
        block = parse_blocks(cleaned)
        assert block.block_type == "ModifiedRecipes"

    def test_added_recipes(self) -> None:
        cleaned = "AddedRecipes:(ItemID:Test;)"
        block = parse_blocks(cleaned)
        assert block.block_type == "AddedRecipes"

    def test_custom_sizes(self) -> None:
        cleaned = "CustomSizes:(ItemID:seat;Width:1;Height:2;)"
        block = parse_blocks(cleaned)
        assert block.block_type == "CustomSizes"

    def test_custom_fabricators(self) -> None:
        cleaned = "CustomFabricators:(ItemID:MyFab;)"
        block = parse_blocks(cleaned)
        assert block.block_type == "CustomFabricators"

    def test_all_ten_block_types(self) -> None:
        """Every CC3 block type keyword parses correctly."""
        block_types = [
            "ModifiedRecipes",
            "AddedRecipes",
            "AliasRecipes",
            "CustomCraftingTabs",
            "CustomFabricators",
            "MovedRecipes",
            "CustomSizes",
            "CustomBioFuels",
            "CustomFragmentCounts",
            "CustomFoods",
        ]
        for bt in block_types:
            cleaned = f"{bt}:(ItemID:test;)"
            block = parse_blocks(cleaned)
            assert block.block_type == bt


# ---------------------------------------------------------------------------
# parse_blocks -- error handling
# ---------------------------------------------------------------------------


class TestParseBlocksErrors:
    """ParseError is raised for malformed input."""

    def test_empty_string(self) -> None:
        with pytest.raises(ParseError):
            parse_blocks("")

    def test_no_colon_after_block_type(self) -> None:
        with pytest.raises(ParseError, match="Expected ':'"):
            parse_blocks("NoColonHere")

    def test_unclosed_paren(self) -> None:
        with pytest.raises(ParseError, match="Expected '\\)'"):
            parse_blocks("Test:(ItemID:test;")


# ---------------------------------------------------------------------------
# parse_blocks -- single entry parsing
# ---------------------------------------------------------------------------


class TestParseBlocksSingleEntry:
    """Parsing a block with one entry."""

    def test_single_field(self) -> None:
        cleaned = "Test:(ItemID:Titanium;)"
        block = parse_blocks(cleaned)
        assert len(block.entries) == 1
        assert block.entries[0].fields["itemid"] == "Titanium"

    def test_multiple_fields(self) -> None:
        cleaned = "Test:(ItemID:Titanium;AmountCrafted:4;)"
        block = parse_blocks(cleaned)
        entry = block.entries[0]
        assert entry.fields["itemid"] == "Titanium"
        assert entry.fields["amountcrafted"] == "4"

    def test_entry_terminated_by_semicolon(self) -> None:
        """Single entry with ');' terminator (common in real files)."""
        cleaned = "AddedRecipes:(ItemID:bigfilteredwater;AmountCrafted:1;);"
        block = parse_blocks(cleaned)
        assert len(block.entries) == 1
        assert block.entries[0].fields["itemid"] == "bigfilteredwater"

    def test_entry_without_trailing_semicolon(self) -> None:
        """Entry without ';' after ')' (e.g. at EOF) still parses."""
        cleaned = "Test:(ItemID:Titanium;AmountCrafted:1;)"
        block = parse_blocks(cleaned)
        assert len(block.entries) == 1


# ---------------------------------------------------------------------------
# parse_blocks -- multiple entries
# ---------------------------------------------------------------------------


class TestParseBlocksMultipleEntries:
    """Parsing blocks with comma-separated entries."""

    def test_two_entries(self) -> None:
        cleaned = "ModifiedRecipes:(ItemID:Titanium;),(ItemID:Gold;);"
        block = parse_blocks(cleaned)
        assert len(block.entries) == 2
        assert block.entries[0].fields["itemid"] == "Titanium"
        assert block.entries[1].fields["itemid"] == "Gold"

    def test_three_entries(self) -> None:
        cleaned = (
            "ModifiedRecipes:"
            "(ItemID:A;AmountCrafted:1;),"
            "(ItemID:B;AmountCrafted:2;),"
            "(ItemID:C;AmountCrafted:3;);"
        )
        block = parse_blocks(cleaned)
        assert len(block.entries) == 3
        assert block.entries[2].fields["amountcrafted"] == "3"

    def test_last_entry_terminated_by_semicolon(self) -> None:
        """The ';' after the last entry terminates the entry list."""
        cleaned = "Test:(ItemID:A;),(ItemID:B;);"
        block = parse_blocks(cleaned)
        assert len(block.entries) == 2


# ---------------------------------------------------------------------------
# parse_blocks -- case-insensitive keys
# ---------------------------------------------------------------------------


class TestParseBlocksCaseInsensitive:
    """Keys are lowercased for case-insensitive lookup."""

    def test_keys_are_lowercased(self) -> None:
        cleaned = "Test:(ItemID:Titanium;AmountCrafted:4;)"
        entry = parse_blocks(cleaned).entries[0]
        assert "itemid" in entry.fields
        assert "amountcrafted" in entry.fields

    def test_mixed_case_keys(self) -> None:
        cleaned = "Test:(ITEMID:A;itemid:B;)"
        entry = parse_blocks(cleaned).entries[0]
        # Second write overwrites the first (both normalize to same key)
        assert "itemid" in entry.fields

    def test_values_preserve_case(self) -> None:
        """Values are NOT lowercased -- only keys are."""
        cleaned = "Test:(ItemID:TitaniumIngot;)"
        entry = parse_blocks(cleaned).entries[0]
        assert entry.fields["itemid"] == "TitaniumIngot"


# ---------------------------------------------------------------------------
# parse_blocks -- nested entry lists (Ingredients)
# ---------------------------------------------------------------------------


class TestParseBlocksNestedEntries:
    """Nested (...)  blocks like Ingredients are parsed into sub_entries."""

    def test_single_ingredient(self) -> None:
        cleaned = "Test:(ItemID:A;Ingredients:(ItemID:Gold;Required:2;);)"
        entry = parse_blocks(cleaned).entries[0]
        assert "ingredients" in entry.sub_entries
        ingredients = entry.sub_entries["ingredients"]
        assert len(ingredients) == 1
        assert ingredients[0].fields["itemid"] == "Gold"
        assert ingredients[0].fields["required"] == "2"

    def test_multiple_ingredients(self) -> None:
        cleaned = (
            "Test:(ItemID:FiberMesh;AmountCrafted:1;"
            "Ingredients:"
            "(ItemID:CreepvinePiece;Required:1;),"
            "(ItemID:PurpleFanSeed;Required:1;);"
            ")"
        )
        entry = parse_blocks(cleaned).entries[0]
        assert entry.fields["itemid"] == "FiberMesh"
        ingredients = entry.sub_entries["ingredients"]
        assert len(ingredients) == 2
        assert ingredients[0].fields["itemid"] == "CreepvinePiece"
        assert ingredients[1].fields["itemid"] == "PurpleFanSeed"

    def test_fields_after_nested_block(self) -> None:
        """Fields appearing after a nested entry list are still parsed."""
        cleaned = (
            "AddedRecipes:(ItemID:bigfilteredwater;AmountCrafted:1;"
            "Ingredients:(ItemID:bleach;Required:1;);"
            "Path:Fabricator/Survival/Water;"
            "ForceUnlockAtStart:NO;);"
        )
        entry = parse_blocks(cleaned).entries[0]
        assert entry.fields["path"] == "Fabricator/Survival/Water"
        assert entry.fields["forceunlockatstart"] == "NO"
        assert len(entry.sub_entries["ingredients"]) == 1

    def test_nested_sub_entries_keys_are_lowercased(self) -> None:
        cleaned = "Test:(Ingredients:(ItemID:X;Required:1;);)"
        entry = parse_blocks(cleaned).entries[0]
        assert "ingredients" in entry.sub_entries
        sub = entry.sub_entries["ingredients"][0]
        assert "itemid" in sub.fields
        assert "required" in sub.fields


# ---------------------------------------------------------------------------
# parse_blocks -- comma-separated values (LinkedItemIDs)
# ---------------------------------------------------------------------------


class TestParseBlocksCommaSeparatedValues:
    """Simple comma-separated values (like LinkedItemIDs) stay as one string."""

    def test_linked_item_ids_single(self) -> None:
        cleaned = "Test:(ItemID:A;LinkedItemIDs:LabEquipment3;)"
        entry = parse_blocks(cleaned).entries[0]
        assert entry.fields["linkeditemids"] == "LabEquipment3"

    def test_linked_item_ids_multiple(self) -> None:
        cleaned = "Test:(ItemID:A;LinkedItemIDs:X,Y,Z;)"
        entry = parse_blocks(cleaned).entries[0]
        # Commas are preserved in the raw value -- step 2c will split them
        assert entry.fields["linkeditemids"] == "X,Y,Z"

    def test_linked_item_ids_with_duplicates(self) -> None:
        """Real CC3 files repeat item IDs to produce multiple outputs."""
        cleaned = "Test:(ItemID:A;LinkedItemIDs:Gold,Gold,Gold,Silver;)"
        entry = parse_blocks(cleaned).entries[0]
        assert entry.fields["linkeditemids"] == "Gold,Gold,Gold,Silver"


# ---------------------------------------------------------------------------
# parse_blocks -- optional semicolons
# ---------------------------------------------------------------------------


class TestParseBlocksOptionalSemicolons:
    """Semicolons are sometimes omitted, especially at end of entries."""

    def test_last_field_no_semicolon(self) -> None:
        """A field right before ')' with no trailing ';' still parses."""
        cleaned = "Test:(ItemID:Titanium)"
        entry = parse_blocks(cleaned).entries[0]
        assert entry.fields["itemid"] == "Titanium"

    def test_entry_list_no_trailing_semicolon(self) -> None:
        """Entry list ending with ')' and no ';' still parses all entries."""
        cleaned = "Test:(ItemID:A;),(ItemID:B;)"
        block = parse_blocks(cleaned)
        assert len(block.entries) == 2


# ---------------------------------------------------------------------------
# parse_blocks -- escape / quote handling in values
# ---------------------------------------------------------------------------


class TestParseBlocksEscapesAndQuotes:
    """Escaped and quoted values pass through the block parser correctly."""

    def test_escaped_colon_in_value(self) -> None:
        r"""A \: in a value is not treated as a key delimiter."""
        cleaned = r"Test:(Key:Value\:More;)"
        entry = parse_blocks(cleaned).entries[0]
        assert entry.fields["key"] == r"Value\:More"

    def test_escaped_semicolon_in_value(self) -> None:
        r"""A \; in a value is not treated as a value delimiter."""
        cleaned = r"Test:(Key:Value\;More;)"
        entry = parse_blocks(cleaned).entries[0]
        assert entry.fields["key"] == r"Value\;More"

    def test_quoted_value_with_special_chars(self) -> None:
        """Quoted strings preserve colons and semicolons in values."""
        cleaned = 'Test:(DisplayName:"My Item: Special";)'
        entry = parse_blocks(cleaned).entries[0]
        assert entry.fields["displayname"] == '"My Item: Special"'

    def test_quoted_tooltip(self) -> None:
        """Quoted tooltip from AliasRecipe."""
        cleaned = 'Test:(Tooltip:"A useful item for crafting";)'
        entry = parse_blocks(cleaned).entries[0]
        assert entry.fields["tooltip"] == '"A useful item for crafting"'


# ---------------------------------------------------------------------------
# parse_blocks -- realistic reference file snippets
# ---------------------------------------------------------------------------


class TestParseBlocksRealisticSnippets:
    """End-to-end tests using snippets from actual CC3 reference files."""

    def test_basic_materials_titanium(self) -> None:
        """First entry from Resources_BasicMaterials.txt."""
        raw = (
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    AmountCrafted: 4;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: ScrapMetal;\n"
            "        Required: 1;\n"
            "    );\n"
            ");\n"
        )
        cleaned = clean_value(raw)
        block = parse_blocks(cleaned)
        assert block.block_type == "ModifiedRecipes"
        assert len(block.entries) == 1
        entry = block.entries[0]
        assert entry.fields["itemid"] == "Titanium"
        assert entry.fields["amountcrafted"] == "4"
        ingredients = entry.sub_entries["ingredients"]
        assert len(ingredients) == 1
        assert ingredients[0].fields["itemid"] == "ScrapMetal"
        assert ingredients[0].fields["required"] == "1"

    def test_basic_materials_fiber_mesh(self) -> None:
        """FiberMesh entry with two ingredients."""
        raw = (
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: FiberMesh;\n"
            "    AmountCrafted: 1;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: CreepvinePiece;\n"
            "        Required: 1;\n"
            "    ),\n"
            "    (\n"
            "        ItemID: PurpleFanSeed;\n"
            "        Required: 1;\n"
            "    );\n"
            ");\n"
        )
        cleaned = clean_value(raw)
        block = parse_blocks(cleaned)
        entry = block.entries[0]
        ingredients = entry.sub_entries["ingredients"]
        assert len(ingredients) == 2
        assert ingredients[0].fields["itemid"] == "CreepvinePiece"
        assert ingredients[1].fields["itemid"] == "PurpleFanSeed"

    def test_basic_materials_with_linked_items(self) -> None:
        """Entry with LinkedItemIDs (comma-separated output items)."""
        raw = (
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Alch_LabContainer3;\n"
            "    AmountCrafted: 0;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: Glass;\n"
            "        Required: 1;\n"
            "    );\n"
            "    LinkedItemIDs: Alch_LabContainer3,Alch_LabContainer3;\n"
            ");\n"
        )
        cleaned = clean_value(raw)
        block = parse_blocks(cleaned)
        entry = block.entries[0]
        assert entry.fields["itemid"] == "Alch_LabContainer3"
        assert entry.fields["amountcrafted"] == "0"
        assert entry.fields["linkeditemids"] == "Alch_LabContainer3,Alch_LabContainer3"
        assert len(entry.sub_entries["ingredients"]) == 1

    def test_big_filtered_water(self) -> None:
        """Full BigFilteredWater.txt -- AddedRecipe with Path and UnlockedBy."""
        raw = (
            "AddedRecipes:\n"
            "(\n"
            "    ItemID: bigfilteredwater;\n"
            "    AmountCrafted: 1;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: bleach;\n"
            "        Required: 1;\n"
            "    );\n"
            "    Path: Fabricator/Survival/Water;\n"
            "    UnlockedBy: disinfectedwater;\n"
            "    ForceUnlockAtStart: NO;\n"
            ");\n"
        )
        cleaned = clean_value(raw)
        block = parse_blocks(cleaned)
        assert block.block_type == "AddedRecipes"
        assert len(block.entries) == 1
        entry = block.entries[0]
        assert entry.fields["itemid"] == "bigfilteredwater"
        assert entry.fields["amountcrafted"] == "1"
        assert entry.fields["path"] == "Fabricator/Survival/Water"
        assert entry.fields["unlockedby"] == "disinfectedwater"
        assert entry.fields["forceunlockatstart"] == "NO"
        assert len(entry.sub_entries["ingredients"]) == 1

    def test_custom_sizes(self) -> None:
        """Snippet from customsizze.txt -- CustomSizes with no nested blocks."""
        raw = (
            "CustomSizes:\n"
            "(\n"
            "\tItemID:seat;\n"
            "    Width:1;\n"
            "    Height:2;\n"
            "),\n"
            "(\n"
            "\tItemID:hulk;\n"
            "    Width:3;\n"
            "    Height:3;\n"
            ");\n"
        )
        cleaned = clean_value(raw)
        block = parse_blocks(cleaned)
        assert block.block_type == "CustomSizes"
        assert len(block.entries) == 2
        assert block.entries[0].fields["itemid"] == "seat"
        assert block.entries[0].fields["width"] == "1"
        assert block.entries[0].fields["height"] == "2"
        assert block.entries[1].fields["itemid"] == "hulk"
        assert block.entries[1].fields["width"] == "3"

    def test_multiple_recipes_basic_materials(self) -> None:
        """Multiple entries from Resources_BasicMaterials.txt."""
        raw = (
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    AmountCrafted: 4;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: ScrapMetal;\n"
            "        Required: 1;\n"
            "    );\n"
            "),\n"
            "(\n"
            "    ItemID: TitaniumIngot;\n"
            "    AmountCrafted: 1;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: Titanium;\n"
            "        Required: 10;\n"
            "    );\n"
            ");\n"
        )
        cleaned = clean_value(raw)
        block = parse_blocks(cleaned)
        assert len(block.entries) == 2
        assert block.entries[0].fields["itemid"] == "Titanium"
        assert block.entries[1].fields["itemid"] == "TitaniumIngot"
        assert block.entries[1].sub_entries["ingredients"][0].fields["required"] == "10"

    def test_four_ingredient_recipe(self) -> None:
        """EnameledGlass with 4 ingredients."""
        raw = (
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: EnameledGlass;\n"
            "    AmountCrafted: 2;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: StalkerTooth;\n"
            "        Required: 3;\n"
            "    ),\n"
            "    (\n"
            "        ItemID: Diamond;\n"
            "        Required: 1;\n"
            "    ),\n"
            "    (\n"
            "        ItemID: Lithium;\n"
            "        Required: 1;\n"
            "    ),\n"
            "    (\n"
            "        ItemID: Glass;\n"
            "        Required: 3;\n"
            "    );\n"
            ");\n"
        )
        cleaned = clean_value(raw)
        block = parse_blocks(cleaned)
        entry = block.entries[0]
        assert entry.fields["amountcrafted"] == "2"
        ingredients = entry.sub_entries["ingredients"]
        assert len(ingredients) == 4
        assert ingredients[0].fields["itemid"] == "StalkerTooth"
        assert ingredients[3].fields["itemid"] == "Glass"
        assert ingredients[3].fields["required"] == "3"

    def test_no_space_after_key_colon(self) -> None:
        """Json2EasyMarkup tool omits spaces: 'ItemID:Titanium;' (no space)."""
        cleaned = "ModifiedRecipes:(ItemID:Titanium;AmountCrafted:1;)"
        block = parse_blocks(cleaned)
        entry = block.entries[0]
        assert entry.fields["itemid"] == "Titanium"
        assert entry.fields["amountcrafted"] == "1"

    def test_with_block_comments(self) -> None:
        """File-level comments (stripped by clean_value) don't interfere."""
        raw = (
            "# This file was generated #\n"
            "# PdaGroup: Resources #\n"
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    AmountCrafted: 4;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: ScrapMetal;\n"
            "        Required: 1;\n"
            "    );\n"
            ");\n"
        )
        cleaned = clean_value(raw)
        block = parse_blocks(cleaned)
        assert block.block_type == "ModifiedRecipes"
        assert block.entries[0].fields["itemid"] == "Titanium"


# ---------------------------------------------------------------------------
# resolve_block_type
# ---------------------------------------------------------------------------


class TestResolveBlockType:
    """Test block type string to BlockType enum resolution."""

    def test_all_ten_types(self) -> None:
        """Every known block type string resolves correctly."""
        for bt in BlockType:
            assert resolve_block_type(bt.value) is bt

    def test_case_insensitive(self) -> None:
        assert resolve_block_type("modifiedrecipes") is BlockType.MODIFIED_RECIPES
        assert resolve_block_type("ADDEDRECIPES") is BlockType.ADDED_RECIPES
        assert resolve_block_type("CustomFabricators") is BlockType.CUSTOM_FABRICATORS

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(MappingError, match="Unknown block type"):
            resolve_block_type("BogusBlock")


# ---------------------------------------------------------------------------
# map_modified_recipe
# ---------------------------------------------------------------------------


class TestMapModifiedRecipe:
    """Test mapping EntryBlock to ModifiedRecipe."""

    def test_minimal(self) -> None:
        entry = EntryBlock(fields={"itemid": "Titanium"})
        recipe = map_modified_recipe(entry)
        assert isinstance(recipe, ModifiedRecipe)
        assert recipe.item_id == "Titanium"
        assert recipe.amount_crafted == 1
        assert recipe.ingredients == []
        assert recipe.linked_item_ids == []

    def test_missing_itemid_raises(self) -> None:
        entry = EntryBlock(fields={"amountcrafted": "2"})
        with pytest.raises(MappingError, match="itemid"):
            map_modified_recipe(entry)

    def test_full_fields(self) -> None:
        entry = EntryBlock(
            fields={
                "itemid": "Titanium",
                "amountcrafted": "4",
                "linkeditemids": "ScrapMetal,Copper",
                "forceunlockatstart": "YES",
                "unlockedby": "Scanner,Knife",
            },
            sub_entries={
                "ingredients": [
                    EntryBlock(fields={"itemid": "ScrapMetal", "required": "1"}),
                ]
            },
        )
        recipe = map_modified_recipe(entry)
        assert recipe.item_id == "Titanium"
        assert recipe.amount_crafted == 4
        assert recipe.ingredients == [Ingredient("ScrapMetal", 1)]
        assert recipe.linked_item_ids == ["ScrapMetal", "Copper"]
        assert recipe.force_unlock_at_start is True
        assert recipe.unlocked_by == ["Scanner", "Knife"]

    def test_multiple_ingredients(self) -> None:
        entry = EntryBlock(
            fields={"itemid": "FiberMesh", "amountcrafted": "1"},
            sub_entries={
                "ingredients": [
                    EntryBlock(fields={"itemid": "CreepvinePiece", "required": "1"}),
                    EntryBlock(fields={"itemid": "PurpleFanSeed", "required": "1"}),
                ]
            },
        )
        recipe = map_modified_recipe(entry)
        assert len(recipe.ingredients) == 2
        assert recipe.ingredients[0] == Ingredient("CreepvinePiece", 1)
        assert recipe.ingredients[1] == Ingredient("PurpleFanSeed", 1)

    def test_unescape_quoted_values(self) -> None:
        """Values containing quote delimiters are unescaped by the mapper."""
        entry = EntryBlock(fields={"itemid": '"Quoted Item"'})
        recipe = map_modified_recipe(entry)
        assert recipe.item_id == "Quoted Item"

    def test_force_unlock_no(self) -> None:
        entry = EntryBlock(fields={"itemid": "Test", "forceunlockatstart": "NO"})
        recipe = map_modified_recipe(entry)
        assert recipe.force_unlock_at_start is False

    def test_force_unlock_absent(self) -> None:
        entry = EntryBlock(fields={"itemid": "Test"})
        recipe = map_modified_recipe(entry)
        assert recipe.force_unlock_at_start is None


# ---------------------------------------------------------------------------
# map_added_recipe
# ---------------------------------------------------------------------------


class TestMapAddedRecipe:
    """Test mapping EntryBlock to AddedRecipe."""

    def test_with_path_and_unlock(self) -> None:
        entry = EntryBlock(
            fields={
                "itemid": "bigfilteredwater",
                "amountcrafted": "1",
                "path": "Fabricator/Survival/Water",
                "unlockedby": "disinfectedwater",
                "forceunlockatstart": "NO",
            },
            sub_entries={
                "ingredients": [
                    EntryBlock(fields={"itemid": "bleach", "required": "1"}),
                ]
            },
        )
        recipe = map_added_recipe(entry)
        assert isinstance(recipe, AddedRecipe)
        assert recipe.item_id == "bigfilteredwater"
        assert recipe.path == "Fabricator/Survival/Water"
        assert recipe.unlocked_by == ["disinfectedwater"]
        assert recipe.force_unlock_at_start is False
        assert recipe.ingredients == [Ingredient("bleach", 1)]

    def test_defaults(self) -> None:
        entry = EntryBlock(fields={"itemid": "Test"})
        recipe = map_added_recipe(entry)
        assert recipe.path == ""
        assert recipe.pda_group is None
        assert recipe.pda_category is None


# ---------------------------------------------------------------------------
# map_alias_recipe
# ---------------------------------------------------------------------------


class TestMapAliasRecipe:
    """Test mapping EntryBlock to AliasRecipe."""

    def test_full_alias(self) -> None:
        entry = EntryBlock(
            fields={
                "itemid": "GallonWater",
                "displayname": '"Water Jug - 1 gallon"',
                "tooltip": '"Large water jug."',
                "amountcrafted": "1",
                "path": "Fabricator/Survival/Water",
            },
            sub_entries={
                "ingredients": [
                    EntryBlock(fields={"itemid": "DisinfectedWater", "required": "10"}),
                ]
            },
        )
        recipe = map_alias_recipe(entry)
        assert isinstance(recipe, AliasRecipe)
        assert recipe.display_name == "Water Jug - 1 gallon"
        assert recipe.tooltip == "Large water jug."
        assert recipe.item_id == "GallonWater"

    def test_with_linked_items(self) -> None:
        entry = EntryBlock(
            fields={
                "itemid": "WaterFromGallon",
                "displayname": '"Disinfected water (x10)"',
                "tooltip": '"Split the jug"',
                "linkeditemids": "DisinfectedWater,DisinfectedWater,DisinfectedWater",
                "amountcrafted": "0",
                "path": "Fabricator/Survival/Water",
            },
        )
        recipe = map_alias_recipe(entry)
        assert recipe.amount_crafted == 0
        assert recipe.linked_item_ids == [
            "DisinfectedWater",
            "DisinfectedWater",
            "DisinfectedWater",
        ]


# ---------------------------------------------------------------------------
# map_custom_food
# ---------------------------------------------------------------------------


class TestMapCustomFood:
    """Test mapping EntryBlock to CustomFood."""

    def test_peeperburger(self) -> None:
        entry = EntryBlock(
            fields={
                "itemid": "Peeperburger",
                "displayname": '"Peeperburger"',
                "tooltip": '"Made from peepers"',
                "amountcrafted": "1",
                "decayratemod": "0.5",
                "path": "Fabricator/CustomFood3/Food",
                "foodvalue": "20",
                "watervalue": "11",
                "forceunlockatstart": "YES",
            },
            sub_entries={
                "ingredients": [
                    EntryBlock(fields={"itemid": "Peeper", "required": "2"}),
                    EntryBlock(fields={"itemid": "CoralChunk", "required": "2"}),
                    EntryBlock(fields={"itemid": "CreepvinePiece", "required": "1"}),
                ]
            },
        )
        food = map_custom_food(entry)
        assert isinstance(food, CustomFood)
        assert food.food_value == 20
        assert food.water_value == 11
        assert food.decay_rate_mod == 0.5
        assert food.force_unlock_at_start is True
        assert len(food.ingredients) == 3

    def test_defaults(self) -> None:
        entry = EntryBlock(fields={"itemid": "TestFood"})
        food = map_custom_food(entry)
        assert food.food_value == 0
        assert food.water_value == 0
        assert food.oxygen_value == 0
        assert food.health_value == 0
        assert food.decay_rate_mod == 0.0
        assert food.food_type is None
        assert food.use_drink_sound is None


# ---------------------------------------------------------------------------
# map_crafting_tab
# ---------------------------------------------------------------------------


class TestMapCraftingTab:
    """Test mapping EntryBlock to CraftingTab."""

    def test_full_tab(self) -> None:
        entry = EntryBlock(
            fields={
                "tabid": "Doodads",
                "displayname": '"Doodas and Gizmos"',
                "spriteitemid": "AdvancedWiringKit",
                "parenttabpath": "Fabricator/Personal",
            }
        )
        tab = map_crafting_tab(entry)
        assert isinstance(tab, CraftingTab)
        assert tab.tab_id == "Doodads"
        assert tab.display_name == "Doodas and Gizmos"
        assert tab.sprite_item_id == "AdvancedWiringKit"
        assert tab.parent_tab_path == "Fabricator/Personal"

    def test_missing_tabid_raises(self) -> None:
        entry = EntryBlock(fields={"displayname": "Test"})
        with pytest.raises(MappingError, match="tabid"):
            map_crafting_tab(entry)


# ---------------------------------------------------------------------------
# map_moved_recipe
# ---------------------------------------------------------------------------


class TestMapMovedRecipe:
    """Test mapping EntryBlock to MovedRecipe."""

    def test_hidden(self) -> None:
        entry = EntryBlock(
            fields={
                "itemid": "Titanium",
                "oldpath": "Fabricator/Resources/BasicMaterials",
                "hidden": "YES",
            }
        )
        moved = map_moved_recipe(entry)
        assert isinstance(moved, MovedRecipe)
        assert moved.item_id == "Titanium"
        assert moved.old_path == "Fabricator/Resources/BasicMaterials"
        assert moved.hidden is True
        assert moved.copied is False
        assert moved.new_path is None

    def test_moved(self) -> None:
        entry = EntryBlock(
            fields={
                "itemid": "TitaniumIngot",
                "oldpath": "Fabricator/Resources/BasicMaterials",
                "newpath": "Fabricator/MoreIngots/packed/metallic",
            }
        )
        moved = map_moved_recipe(entry)
        assert moved.old_path == "Fabricator/Resources/BasicMaterials"
        assert moved.new_path == "Fabricator/MoreIngots/packed/metallic"

    def test_copied(self) -> None:
        entry = EntryBlock(
            fields={
                "itemid": "HeatBlade",
                "newpath": "Fabricator/Personal/Tools",
                "copied": "YES",
            }
        )
        moved = map_moved_recipe(entry)
        assert moved.copied is True
        assert moved.old_path is None


# ---------------------------------------------------------------------------
# map_custom_size
# ---------------------------------------------------------------------------


class TestMapCustomSize:
    """Test mapping EntryBlock to CustomSize."""

    def test_basic(self) -> None:
        entry = EntryBlock(fields={"itemid": "seat", "width": "1", "height": "2"})
        size = map_custom_size(entry)
        assert isinstance(size, CustomSize)
        assert size.item_id == "seat"
        assert size.width == 1
        assert size.height == 2

    def test_large_size(self) -> None:
        entry = EntryBlock(fields={"itemid": "assemhull", "width": "6", "height": "3"})
        size = map_custom_size(entry)
        assert size.width == 6
        assert size.height == 3


# ---------------------------------------------------------------------------
# map_custom_bio_fuel
# ---------------------------------------------------------------------------


class TestMapCustomBioFuel:
    """Test mapping EntryBlock to CustomBioFuel."""

    def test_basic(self) -> None:
        entry = EntryBlock(fields={"itemid": "Oculus", "energy": "650"})
        fuel = map_custom_bio_fuel(entry)
        assert isinstance(fuel, CustomBioFuel)
        assert fuel.item_id == "Oculus"
        assert fuel.energy == 650.0

    def test_zero_energy(self) -> None:
        entry = EntryBlock(fields={"itemid": "CreepvineSeedCluster", "energy": "0"})
        fuel = map_custom_bio_fuel(entry)
        assert fuel.energy == 0.0


# ---------------------------------------------------------------------------
# map_custom_fragment_count
# ---------------------------------------------------------------------------


class TestMapCustomFragmentCount:
    """Test mapping EntryBlock to CustomFragmentCount."""

    def test_basic(self) -> None:
        entry = EntryBlock(fields={"itemid": "Seaglide", "fragmentstoscan": "4"})
        frag = map_custom_fragment_count(entry)
        assert isinstance(frag, CustomFragmentCount)
        assert frag.item_id == "Seaglide"
        assert frag.fragments_to_scan == 4


# ---------------------------------------------------------------------------
# map_custom_fabricator
# ---------------------------------------------------------------------------


class TestMapCustomFabricator:
    """Test mapping EntryBlock to CustomFabricator."""

    def test_basic_fields(self) -> None:
        entry = EntryBlock(
            fields={
                "itemid": "Seafab",
                "displayname": '"Seamoth Parts Fabricator"',
                "tooltip": '"Fabricate Mechanical Parts"',
                "model": "Workbench",
                "colortint": "0.0,0.1,1.0,1.0",
                "allowedinbase": "YES",
                "allowedincyclops": "YES",
                "forceunlockatstart": "no",
                "unlockedby": "seamoth,workbench",
                "pdagroup": "InteriorModules",
                "pdacategory": "InteriorModule",
            },
            sub_entries={
                "ingredients": [
                    EntryBlock(fields={"itemid": "builder", "required": "2"}),
                    EntryBlock(fields={"itemid": "wiringkit", "required": "1"}),
                ],
            },
        )
        fab = map_custom_fabricator(entry)
        assert isinstance(fab, CustomFabricator)
        assert fab.item_id == "Seafab"
        assert fab.display_name == "Seamoth Parts Fabricator"
        assert fab.model == "Workbench"
        assert fab.color_tint == [0.0, 0.1, 1.0, 1.0]
        assert fab.allowed_in_base is True
        assert fab.allowed_in_cyclops is True
        assert fab.force_unlock_at_start is False
        assert fab.unlocked_by == ["seamoth", "workbench"]
        assert len(fab.ingredients) == 2

    def test_nested_tabs(self) -> None:
        entry = EntryBlock(
            fields={"itemid": "TestFab"},
            sub_entries={
                "customcraftingtabs": [
                    EntryBlock(
                        fields={
                            "tabid": "Tab1",
                            "displayname": '"My Tab"',
                            "parenttabpath": "TestFab",
                        }
                    ),
                    EntryBlock(
                        fields={
                            "tabid": "Tab2",
                            "displayname": '"Sub Tab"',
                            "parenttabpath": "TestFab/Tab1",
                        }
                    ),
                ],
            },
        )
        fab = map_custom_fabricator(entry)
        assert len(fab.tabs) == 2
        assert fab.tabs[0].tab_id == "Tab1"
        assert fab.tabs[0].display_name == "My Tab"
        assert fab.tabs[1].parent_tab_path == "TestFab/Tab1"

    def test_nested_alias_recipes(self) -> None:
        entry = EntryBlock(
            fields={"itemid": "TestFab"},
            sub_entries={
                "aliasrecipes": [
                    EntryBlock(
                        fields={
                            "itemid": "seat",
                            "displayname": '"Seamoth Seat"',
                            "tooltip": '"Comfortable seat"',
                            "linkeditemids": "seat",
                            "path": "TestFab/Inside",
                        },
                        sub_entries={
                            "ingredients": [
                                EntryBlock(
                                    fields={
                                        "itemid": "fibermesh",
                                        "required": "2",
                                    }
                                ),
                            ]
                        },
                    ),
                ],
            },
        )
        fab = map_custom_fabricator(entry)
        assert len(fab.alias_recipes) == 1
        alias = fab.alias_recipes[0]
        assert alias.item_id == "seat"
        assert alias.display_name == "Seamoth Seat"
        assert alias.linked_item_ids == ["seat"]
        assert alias.path == "TestFab/Inside"
        assert alias.ingredients == [Ingredient("fibermesh", 2)]

    def test_defaults(self) -> None:
        entry = EntryBlock(fields={"itemid": "MinimalFab"})
        fab = map_custom_fabricator(entry)
        assert fab.model == "Fabricator"
        assert fab.color_tint == []
        assert fab.allowed_in_base is True
        assert fab.allowed_in_cyclops is True
        assert fab.tabs == []
        assert fab.added_recipes == []
        assert fab.alias_recipes == []
        assert fab.moved_recipes == []
        assert fab.custom_foods == []

    def test_nested_moved_recipes(self) -> None:
        entry = EntryBlock(
            fields={"itemid": "TestFab"},
            sub_entries={
                "movedrecipes": [
                    EntryBlock(
                        fields={
                            "itemid": "Titanium",
                            "oldpath": "Fab/Resources",
                            "hidden": "YES",
                        }
                    ),
                ],
            },
        )
        fab = map_custom_fabricator(entry)
        assert len(fab.moved_recipes) == 1
        assert fab.moved_recipes[0].hidden is True


# ---------------------------------------------------------------------------
# End-to-end: clean -> parse -> map pipeline
# ---------------------------------------------------------------------------


class TestCleanParseMapPipeline:
    """Test the full pipeline from raw text to typed models."""

    def test_modified_recipe_pipeline(self) -> None:
        raw = (
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    AmountCrafted: 4;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: ScrapMetal;\n"
            "        Required: 1;\n"
            "    );\n"
            ");\n"
        )
        cleaned = clean_value(raw)
        block = parse_blocks(cleaned)
        bt = resolve_block_type(block.block_type)
        assert bt is BlockType.MODIFIED_RECIPES
        recipe = map_modified_recipe(block.entries[0])
        assert recipe.item_id == "Titanium"
        assert recipe.amount_crafted == 4
        assert recipe.ingredients == [Ingredient("ScrapMetal", 1)]

    def test_custom_sizes_pipeline(self) -> None:
        raw = (
            "CustomSizes:\n"
            "(\n"
            "\tItemID:seat;\n"
            "    Width:1;\n"
            "    Height:2;\n"
            "),\n"
            "(\n"
            "\tItemID:hulk;\n"
            "    Width:3;\n"
            "    Height:3;\n"
            ");\n"
        )
        cleaned = clean_value(raw)
        block = parse_blocks(cleaned)
        bt = resolve_block_type(block.block_type)
        assert bt is BlockType.CUSTOM_SIZES
        sizes = [map_custom_size(e) for e in block.entries]
        assert len(sizes) == 2
        assert sizes[0] == CustomSize("seat", 1, 2)
        assert sizes[1] == CustomSize("hulk", 3, 3)

    def test_added_recipe_pipeline(self) -> None:
        raw = (
            "AddedRecipes:\n"
            "(\n"
            "    ItemID: bigfilteredwater;\n"
            "    AmountCrafted: 1;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: bleach;\n"
            "        Required: 1;\n"
            "    );\n"
            "    Path: Fabricator/Survival/Water;\n"
            "    UnlockedBy: disinfectedwater;\n"
            "    ForceUnlockAtStart: NO;\n"
            ");\n"
        )
        cleaned = clean_value(raw)
        block = parse_blocks(cleaned)
        recipe = map_added_recipe(block.entries[0])
        assert recipe.item_id == "bigfilteredwater"
        assert recipe.path == "Fabricator/Survival/Water"
        assert recipe.unlocked_by == ["disinfectedwater"]
        assert recipe.force_unlock_at_start is False

    def test_custom_bio_fuels_pipeline(self) -> None:
        raw = (
            "CustomBioFuels:\n"
            "(\n"
            "    ItemID: Oculus;\n"
            "    Energy: 650;\n"
            "),\n"
            "(\n"
            "    ItemID: NutrientBlock;\n"
            "    Energy: 400;\n"
            ");\n"
        )
        cleaned = clean_value(raw)
        block = parse_blocks(cleaned)
        fuels = [map_custom_bio_fuel(e) for e in block.entries]
        assert len(fuels) == 2
        assert fuels[0] == CustomBioFuel("Oculus", 650.0)
        assert fuels[1] == CustomBioFuel("NutrientBlock", 400.0)

    def test_custom_fragment_counts_pipeline(self) -> None:
        raw = (
            "CustomFragmentCounts:\n"
            "(\n"
            "    ItemID: Seaglide;\n"
            "    FragmentsToScan: 4;\n"
            "),\n"
            "(\n"
            "    ItemID: Seamoth;\n"
            "    FragmentsToScan: 6;\n"
            ");\n"
        )
        cleaned = clean_value(raw)
        block = parse_blocks(cleaned)
        frags = [map_custom_fragment_count(e) for e in block.entries]
        assert len(frags) == 2
        assert frags[0] == CustomFragmentCount("Seaglide", 4)
        assert frags[1] == CustomFragmentCount("Seamoth", 6)


# ---------------------------------------------------------------------------
# parse_file
# ---------------------------------------------------------------------------


class TestParseFile:
    """Test the top-level parse_file function."""

    def test_modified_recipes(self, tmp_path: Path) -> None:
        f = tmp_path / "recipes.txt"
        f.write_text(
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    AmountCrafted: 4;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: ScrapMetal;\n"
            "        Required: 1;\n"
            "    );\n"
            ");\n",
            encoding="utf-8",
        )
        result = parse_file(f)
        assert result.source_path == f
        assert result.block_type is BlockType.MODIFIED_RECIPES
        assert len(result.modified_recipes) == 1
        assert result.modified_recipes[0].item_id == "Titanium"
        assert result.modified_recipes[0].amount_crafted == 4
        assert result.modified_recipes[0].ingredients == [Ingredient("ScrapMetal", 1)]
        # Other lists remain empty
        assert result.added_recipes == []
        assert result.custom_sizes == []

    def test_custom_sizes(self, tmp_path: Path) -> None:
        f = tmp_path / "sizes.txt"
        f.write_text(
            "CustomSizes:\n"
            "(ItemID:seat; Width:1; Height:2;),\n"
            "(ItemID:hulk; Width:3; Height:3;);\n",
            encoding="utf-8",
        )
        result = parse_file(f)
        assert result.block_type is BlockType.CUSTOM_SIZES
        assert len(result.custom_sizes) == 2
        assert result.custom_sizes[0] == CustomSize("seat", 1, 2)
        assert result.custom_sizes[1] == CustomSize("hulk", 3, 3)

    def test_added_recipe_with_unlock(self, tmp_path: Path) -> None:
        f = tmp_path / "added.txt"
        f.write_text(
            "AddedRecipes:\n"
            "(\n"
            "    ItemID: bigfilteredwater;\n"
            "    AmountCrafted: 1;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: bleach;\n"
            "        Required: 1;\n"
            "    );\n"
            "    Path: Fabricator/Survival/Water;\n"
            "    UnlockedBy: disinfectedwater;\n"
            "    ForceUnlockAtStart: NO;\n"
            ");\n",
            encoding="utf-8",
        )
        result = parse_file(f)
        assert result.block_type is BlockType.ADDED_RECIPES
        assert len(result.added_recipes) == 1
        r = result.added_recipes[0]
        assert r.path == "Fabricator/Survival/Water"
        assert r.unlocked_by == ["disinfectedwater"]
        assert r.force_unlock_at_start is False

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        result = parse_file(f)
        assert result.source_path == f
        assert result.block_type is None
        assert result.modified_recipes == []

    def test_comment_only_file(self, tmp_path: Path) -> None:
        f = tmp_path / "comments.txt"
        f.write_text("# this file has only comments #\n", encoding="utf-8")
        result = parse_file(f)
        assert result.block_type is None

    def test_alias_recipes(self, tmp_path: Path) -> None:
        f = tmp_path / "alias.txt"
        f.write_text(
            "AliasRecipes:\n"
            "(\n"
            "    ItemID: GallonWater;\n"
            '    DisplayName: "Water Jug";\n'
            '    Tooltip: "Large jug";\n'
            "    AmountCrafted: 1;\n"
            "    Path: Fabricator/Survival/Water;\n"
            ");\n",
            encoding="utf-8",
        )
        result = parse_file(f)
        assert result.block_type is BlockType.ALIAS_RECIPES
        assert len(result.alias_recipes) == 1
        assert result.alias_recipes[0].display_name == "Water Jug"

    def test_custom_bio_fuels(self, tmp_path: Path) -> None:
        f = tmp_path / "biofuel.txt"
        f.write_text(
            "CustomBioFuels:\n(ItemID: Oculus; Energy: 650;);\n",
            encoding="utf-8",
        )
        result = parse_file(f)
        assert result.block_type is BlockType.CUSTOM_BIO_FUELS
        assert len(result.custom_bio_fuels) == 1
        assert result.custom_bio_fuels[0] == CustomBioFuel("Oculus", 650.0)

    def test_custom_fragment_counts(self, tmp_path: Path) -> None:
        f = tmp_path / "frags.txt"
        f.write_text(
            "CustomFragmentCounts:\n(ItemID: Seaglide; FragmentsToScan: 4;);\n",
            encoding="utf-8",
        )
        result = parse_file(f)
        assert result.block_type is BlockType.CUSTOM_FRAGMENT_COUNTS
        assert result.custom_fragment_counts[0] == CustomFragmentCount("Seaglide", 4)

    def test_moved_recipes(self, tmp_path: Path) -> None:
        f = tmp_path / "moved.txt"
        f.write_text(
            "MovedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    OldPath: Fabricator/Resources/BasicMaterials;\n"
            "    Hidden: YES;\n"
            ");\n",
            encoding="utf-8",
        )
        result = parse_file(f)
        assert result.block_type is BlockType.MOVED_RECIPES
        assert len(result.moved_recipes) == 1
        assert result.moved_recipes[0].hidden is True

    def test_custom_foods(self, tmp_path: Path) -> None:
        f = tmp_path / "foods.txt"
        f.write_text(
            "CustomFoods:\n"
            "(\n"
            "    ItemID: Burger;\n"
            '    DisplayName: "Burger";\n'
            '    Tooltip: "Tasty";\n'
            "    FoodValue: 20;\n"
            "    WaterValue: 10;\n"
            "    Path: Fabricator/Food;\n"
            ");\n",
            encoding="utf-8",
        )
        result = parse_file(f)
        assert result.block_type is BlockType.CUSTOM_FOODS
        assert len(result.custom_foods) == 1
        assert result.custom_foods[0].food_value == 20

    def test_custom_crafting_tabs(self, tmp_path: Path) -> None:
        f = tmp_path / "tabs.txt"
        f.write_text(
            "CustomCraftingTabs:\n"
            "(\n"
            "    TabID: MyTab;\n"
            '    DisplayName: "My Tab";\n'
            "    SpriteItemID: Titanium;\n"
            "    ParentTabPath: Fabricator/Personal;\n"
            ");\n",
            encoding="utf-8",
        )
        result = parse_file(f)
        assert result.block_type is BlockType.CUSTOM_CRAFTING_TABS
        assert len(result.crafting_tabs) == 1
        assert result.crafting_tabs[0].tab_id == "MyTab"

    def test_custom_fabricators(self, tmp_path: Path) -> None:
        f = tmp_path / "fab.txt"
        f.write_text(
            "CustomFabricators:\n"
            "(\n"
            "    ItemID: MyFab;\n"
            '    DisplayName: "My Fabricator";\n'
            "    Model: Workbench;\n"
            "    AliasRecipes:\n"
            "    (\n"
            "        ItemID: widget;\n"
            '        DisplayName: "Widget";\n'
            '        Tooltip: "A widget";\n'
            "        Path: MyFab/Stuff;\n"
            "    );\n"
            ");\n",
            encoding="utf-8",
        )
        result = parse_file(f)
        assert result.block_type is BlockType.CUSTOM_FABRICATORS
        assert len(result.custom_fabricators) == 1
        fab = result.custom_fabricators[0]
        assert fab.item_id == "MyFab"
        assert fab.model == "Workbench"
        assert len(fab.alias_recipes) == 1
        assert fab.alias_recipes[0].item_id == "widget"

    def test_all_recipes_property(self, tmp_path: Path) -> None:
        """ParsedFile.all_recipes aggregates across nested fabricator recipes."""
        f = tmp_path / "fab.txt"
        f.write_text(
            "CustomFabricators:\n"
            "(\n"
            "    ItemID: Fab;\n"
            "    AddedRecipes:\n"
            "    (\n"
            "        ItemID: ItemA;\n"
            "        Path: Fab/Tab;\n"
            "    );\n"
            "    AliasRecipes:\n"
            "    (\n"
            "        ItemID: ItemB;\n"
            '        DisplayName: "B";\n'
            '        Tooltip: "B";\n'
            "        Path: Fab/Tab;\n"
            "    );\n"
            ");\n",
            encoding="utf-8",
        )
        result = parse_file(f)
        recipes = result.all_recipes
        ids = [r.item_id for r in recipes]
        assert "ItemA" in ids
        assert "ItemB" in ids


# ---------------------------------------------------------------------------
# parse_directory
# ---------------------------------------------------------------------------


class TestParseDirectory:
    """Test the directory-level parse_directory function."""

    def test_single_file(self, tmp_path: Path) -> None:
        """A directory with one valid .txt file returns one ParsedFile."""
        f = tmp_path / "recipes.txt"
        f.write_text(
            "ModifiedRecipes:\n"
            "(ItemID: Titanium; AmountCrafted: 4;\n"
            "    Ingredients:(ItemID: ScrapMetal; Required: 1;);\n"
            ");\n",
            encoding="utf-8",
        )
        results = parse_directory(tmp_path)
        assert len(results) == 1
        assert results[0].source_path == f
        assert results[0].block_type is BlockType.MODIFIED_RECIPES
        assert results[0].modified_recipes[0].item_id == "Titanium"

    def test_multiple_files(self, tmp_path: Path) -> None:
        """Multiple .txt files are all parsed and returned."""
        (tmp_path / "recipes.txt").write_text(
            "ModifiedRecipes:\n(ItemID: Titanium;);\n",
            encoding="utf-8",
        )
        (tmp_path / "sizes.txt").write_text(
            "CustomSizes:\n(ItemID: seat; Width: 1; Height: 2;);\n",
            encoding="utf-8",
        )
        results = parse_directory(tmp_path)
        assert len(results) == 2
        block_types = {r.block_type for r in results}
        assert BlockType.MODIFIED_RECIPES in block_types
        assert BlockType.CUSTOM_SIZES in block_types

    def test_recursive_subdirectories(self, tmp_path: Path) -> None:
        """Files in subdirectories are discovered recursively."""
        sub = tmp_path / "sub" / "deep"
        sub.mkdir(parents=True)
        (tmp_path / "top.txt").write_text(
            "ModifiedRecipes:\n(ItemID: TopItem;);\n",
            encoding="utf-8",
        )
        (sub / "nested.txt").write_text(
            "AddedRecipes:\n(ItemID: DeepItem; Path: Fab/Tab;);\n",
            encoding="utf-8",
        )
        results = parse_directory(tmp_path)
        assert len(results) == 2
        ids = [r.all_recipes[0].item_id for r in results]
        assert "TopItem" in ids
        assert "DeepItem" in ids

    def test_empty_directory(self, tmp_path: Path) -> None:
        """An empty directory returns an empty list."""
        results = parse_directory(tmp_path)
        assert results == []

    def test_skips_empty_files(self, tmp_path: Path) -> None:
        """Empty .txt files (block_type is None) are filtered out."""
        (tmp_path / "empty.txt").write_text("", encoding="utf-8")
        (tmp_path / "valid.txt").write_text(
            "ModifiedRecipes:\n(ItemID: Titanium;);\n",
            encoding="utf-8",
        )
        results = parse_directory(tmp_path)
        assert len(results) == 1
        assert results[0].modified_recipes[0].item_id == "Titanium"

    def test_skips_comment_only_files(self, tmp_path: Path) -> None:
        """Files containing only comments are filtered out."""
        (tmp_path / "comments.txt").write_text("# this is all comments #\n", encoding="utf-8")
        results = parse_directory(tmp_path)
        assert results == []

    def test_skips_unparseable_files(self, tmp_path: Path) -> None:
        """Files that raise ParseError are skipped, not fatal."""
        (tmp_path / "broken.txt").write_text("not valid easymarkup at all", encoding="utf-8")
        (tmp_path / "valid.txt").write_text(
            "ModifiedRecipes:\n(ItemID: Titanium;);\n",
            encoding="utf-8",
        )
        results = parse_directory(tmp_path)
        assert len(results) == 1
        assert results[0].modified_recipes[0].item_id == "Titanium"

    def test_skips_mapping_error_files(self, tmp_path: Path) -> None:
        """Files that raise MappingError (e.g. missing ItemID) are skipped."""
        (tmp_path / "bad_mapping.txt").write_text(
            "ModifiedRecipes:\n(AmountCrafted: 2;);\n",
            encoding="utf-8",
        )
        (tmp_path / "valid.txt").write_text(
            "AddedRecipes:\n(ItemID: Widget; Path: Fab/Tab;);\n",
            encoding="utf-8",
        )
        results = parse_directory(tmp_path)
        assert len(results) == 1
        assert results[0].added_recipes[0].item_id == "Widget"

    def test_ignores_non_txt_files(self, tmp_path: Path) -> None:
        """Non-.txt files (e.g. .png, .json) are not parsed."""
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        (tmp_path / "data.json").write_text('{"key": "val"}', encoding="utf-8")
        (tmp_path / "recipes.txt").write_text(
            "ModifiedRecipes:\n(ItemID: Titanium;);\n",
            encoding="utf-8",
        )
        results = parse_directory(tmp_path)
        assert len(results) == 1

    def test_nonexistent_directory_raises(self, tmp_path: Path) -> None:
        """FileNotFoundError raised for a path that doesn't exist."""
        with pytest.raises(FileNotFoundError, match="not found"):
            parse_directory(tmp_path / "no_such_dir")

    def test_file_instead_of_directory_raises(self, tmp_path: Path) -> None:
        """NotADirectoryError raised when given a file path."""
        f = tmp_path / "file.txt"
        f.write_text("content", encoding="utf-8")
        with pytest.raises(NotADirectoryError, match="Not a directory"):
            parse_directory(f)

    def test_deterministic_order(self, tmp_path: Path) -> None:
        """Results are sorted by source path for deterministic output."""
        (tmp_path / "z_last.txt").write_text(
            "ModifiedRecipes:\n(ItemID: ZItem;);\n", encoding="utf-8"
        )
        (tmp_path / "a_first.txt").write_text(
            "ModifiedRecipes:\n(ItemID: AItem;);\n", encoding="utf-8"
        )
        (tmp_path / "m_middle.txt").write_text(
            "ModifiedRecipes:\n(ItemID: MItem;);\n", encoding="utf-8"
        )
        results = parse_directory(tmp_path)
        paths = [r.source_path.name for r in results]
        assert paths == ["a_first.txt", "m_middle.txt", "z_last.txt"]

    def test_mixed_valid_and_invalid(self, tmp_path: Path) -> None:
        """A mix of valid, empty, broken, and non-txt files."""
        (tmp_path / "a_valid.txt").write_text(
            "ModifiedRecipes:\n(ItemID: Alpha;);\n", encoding="utf-8"
        )
        (tmp_path / "b_empty.txt").write_text("", encoding="utf-8")
        (tmp_path / "c_broken.txt").write_text("garbage", encoding="utf-8")
        (tmp_path / "d_valid.txt").write_text(
            "CustomSizes:\n(ItemID: Bravo; Width: 2; Height: 3;);\n",
            encoding="utf-8",
        )
        (tmp_path / "not_a_recipe.png").write_bytes(b"\x00")
        results = parse_directory(tmp_path)
        assert len(results) == 2
        assert results[0].modified_recipes[0].item_id == "Alpha"
        assert results[1].custom_sizes[0].item_id == "Bravo"


# ---------------------------------------------------------------------------
# validate_parsed_file -- ingredient range validation
# ---------------------------------------------------------------------------


class TestValidateParsedFile:
    """Post-parse validation: ingredient Required range (CC3 enforces 1-25)."""

    def _make_parsed(
        self,
        ingredients: list[Ingredient] | None = None,
        *,
        fab_ingredients: list[Ingredient] | None = None,
    ) -> ParsedFile:
        """Build a minimal ParsedFile with one recipe and/or one fabricator."""
        pf = ParsedFile(source_path=Path("test.txt"))
        if ingredients is not None:
            pf.modified_recipes = [
                ModifiedRecipe(item_id="TestRecipe", ingredients=ingredients),
            ]
        if fab_ingredients is not None:
            pf.custom_fabricators = [
                CustomFabricator(item_id="TestFab", ingredients=fab_ingredients),
            ]
        return pf

    def test_valid_range_no_warnings(self) -> None:
        """Required=1 (min) and Required=25 (max) produce no warnings."""
        pf = self._make_parsed(
            [
                Ingredient(item_id="A", required=1),
                Ingredient(item_id="B", required=25),
            ]
        )
        assert validate_parsed_file(pf) == []

    def test_required_zero_warns(self) -> None:
        """Required=0 is below minimum, produces a warning."""
        pf = self._make_parsed([Ingredient(item_id="Titanium", required=0)])
        warnings = validate_parsed_file(pf)
        assert len(warnings) == 1
        assert "Required=0" in warnings[0]
        assert "Titanium" in warnings[0]

    def test_required_above_max_warns(self) -> None:
        """Required=26 exceeds maximum, produces a warning."""
        pf = self._make_parsed([Ingredient(item_id="Quartz", required=26)])
        warnings = validate_parsed_file(pf)
        assert len(warnings) == 1
        assert "Required=26" in warnings[0]

    def test_negative_required_warns(self) -> None:
        """Required=-1 is out of range."""
        pf = self._make_parsed([Ingredient(item_id="Glass", required=-1)])
        warnings = validate_parsed_file(pf)
        assert len(warnings) == 1
        assert "Required=-1" in warnings[0]

    def test_multiple_bad_ingredients(self) -> None:
        """Two out-of-range ingredients produce two warnings."""
        pf = self._make_parsed(
            [
                Ingredient(item_id="A", required=0),
                Ingredient(item_id="B", required=5),
                Ingredient(item_id="C", required=99),
            ]
        )
        warnings = validate_parsed_file(pf)
        assert len(warnings) == 2
        warned_ids = {w.split("'")[1] for w in warnings}
        assert warned_ids == {"A", "C"}

    def test_empty_file_no_warnings(self) -> None:
        """An empty ParsedFile (no recipes) produces no warnings."""
        pf = ParsedFile(source_path=Path("empty.txt"))
        assert validate_parsed_file(pf) == []

    def test_fabricator_build_cost_validated(self) -> None:
        """CustomFabricator.ingredients (build cost) are also validated."""
        pf = self._make_parsed(
            fab_ingredients=[
                Ingredient(item_id="Titanium", required=0),
            ]
        )
        warnings = validate_parsed_file(pf)
        assert len(warnings) == 1
        assert "fabricator" in warnings[0]
        assert "Titanium" in warnings[0]

    def test_parsing_not_blocked(self) -> None:
        """Out-of-range Required values still parse into Ingredient."""
        pf = self._make_parsed(
            [
                Ingredient(item_id="X", required=0),
                Ingredient(item_id="Y", required=100),
            ]
        )
        assert len(pf.modified_recipes) == 1
        assert pf.modified_recipes[0].ingredients[0].required == 0
        assert pf.modified_recipes[0].ingredients[1].required == 100


# ---------------------------------------------------------------------------
# Integration tests -- real reference files
# ---------------------------------------------------------------------------

# Root of the cc3_reference_files directory, resolved relative to this test file.
_REF_DIR = Path(__file__).resolve().parent.parent / "craftgraph" / "cc3_reference_files"
_REAL_MOD_EXAMPLES = _REF_DIR / "real-mod-examples"
_SAMPLE_FILES = _REF_DIR / "original-source" / "CustomCraft3" / "SampleFiles"


class TestIntegrationSampleFiles:
    """Integration tests: parse official CC3 SampleFiles (all 10 block types)."""

    def test_modified_recipes(self) -> None:
        result = parse_file(_SAMPLE_FILES / "ModifiedRecipes_Samples.txt")
        assert result.block_type is BlockType.MODIFIED_RECIPES
        assert len(result.modified_recipes) == 4

        welder = result.modified_recipes[0]
        assert welder.item_id == "Welder"
        assert len(welder.ingredients) == 4
        assert welder.ingredients[3] == Ingredient("Battery", 1)

        reactor = result.modified_recipes[2]
        assert reactor.item_id == "ReactorRod"
        assert reactor.unlocks == ["DepletedReactorRod"]

        seaglide = result.modified_recipes[3]
        assert seaglide.item_id == "Seaglide"
        assert seaglide.force_unlock_at_start is True

    def test_added_recipes(self) -> None:
        result = parse_file(_SAMPLE_FILES / "AddedRecipes_Samples.txt")
        assert result.block_type is BlockType.ADDED_RECIPES
        assert len(result.added_recipes) == 1

        rod = result.added_recipes[0]
        assert rod.item_id == "DepletedReactorRod"
        assert rod.path == "Fabricator/Resources/Electronics"
        assert rod.linked_item_ids == ["UraniniteCrystal"] * 3
        assert rod.force_unlock_at_start is False

    def test_alias_recipes(self) -> None:
        result = parse_file(_SAMPLE_FILES / "AliasRecipes_Samples.txt")
        assert result.block_type is BlockType.ALIAS_RECIPES
        assert len(result.alias_recipes) == 2

        gallon = result.alias_recipes[0]
        assert gallon.item_id == "GallonWater"
        assert gallon.display_name == "Water Jug - 1 gallon"
        assert gallon.path == "Fabricator/Survival/Water"

        water = result.alias_recipes[1]
        assert water.item_id == "WaterFromGallon"
        assert water.amount_crafted == 0
        assert len(water.linked_item_ids) == 10

    def test_custom_fabricator(self) -> None:
        result = parse_file(_SAMPLE_FILES / "CustomFabricator_Sample.txt")
        assert result.block_type is BlockType.CUSTOM_FABRICATORS
        assert len(result.custom_fabricators) == 1

        fab = result.custom_fabricators[0]
        assert fab.item_id == "SampleFabricator"
        assert fab.display_name == "Simple Decorations Fabricator"
        assert fab.model == "Workbench"
        assert fab.force_unlock_at_start is True
        assert fab.color_tint == [1.0, 0.64, 0.0]
        assert len(fab.tabs) == 1
        assert fab.tabs[0].tab_id == "ScienceTab"
        assert fab.tabs[0].display_name == "Science!"
        assert len(fab.added_recipes) == 1
        assert fab.added_recipes[0].item_id == "LabEquipment1"

    def test_custom_crafting_tabs(self) -> None:
        result = parse_file(_SAMPLE_FILES / "CustomTab_Samples.txt")
        assert result.block_type is BlockType.CUSTOM_CRAFTING_TABS
        assert len(result.crafting_tabs) == 5

        doodads = result.crafting_tabs[0]
        assert doodads.tab_id == "Doodads"
        assert doodads.display_name == "Doodas and Gizmos"
        assert doodads.sprite_item_id == "AdvancedWiringKit"
        assert doodads.parent_tab_path == "Fabricator/Personal"

    def test_moved_recipes(self) -> None:
        result = parse_file(_SAMPLE_FILES / "MovedRecipes_Samples2.txt")
        assert result.block_type is BlockType.MOVED_RECIPES
        assert len(result.moved_recipes) == 4

        move = result.moved_recipes[0]
        assert move.item_id == "TitaniumIngot"
        assert move.old_path == "Fabricator/Resources/BasicMaterials"
        assert move.new_path == "Fabricator/Resources/AdvancedMaterials"

        hide = result.moved_recipes[1]
        assert hide.item_id == "StasisRifle"
        assert hide.hidden is True

        copy_ = result.moved_recipes[3]
        assert copy_.item_id == "UltraGlideFins"
        assert copy_.copied is True

    def test_custom_sizes(self) -> None:
        result = parse_file(_SAMPLE_FILES / "CustomSizes_Samples.txt")
        assert result.block_type is BlockType.CUSTOM_SIZES
        assert len(result.custom_sizes) == 2
        assert result.custom_sizes[0] == CustomSize("CreepvineSeedCluster", 1, 1)

    def test_custom_bio_fuels(self) -> None:
        result = parse_file(_SAMPLE_FILES / "CustomBioFuels_Samples.txt")
        assert result.block_type is BlockType.CUSTOM_BIO_FUELS
        assert len(result.custom_bio_fuels) == 3

        oculus = result.custom_bio_fuels[0]
        assert oculus.item_id == "Oculus"
        assert oculus.energy == 650

        zero_energy = result.custom_bio_fuels[2]
        assert zero_energy.item_id == "CreepvineSeedCluster"
        assert zero_energy.energy == 0

    def test_custom_fragment_counts(self) -> None:
        result = parse_file(_SAMPLE_FILES / "CustomFragments_Samples2.txt")
        assert result.block_type is BlockType.CUSTOM_FRAGMENT_COUNTS
        assert len(result.custom_fragment_counts) == 3
        assert result.custom_fragment_counts[0].item_id == "Seaglide"
        assert result.custom_fragment_counts[0].fragments_to_scan == 4

    def test_custom_foods(self) -> None:
        result = parse_file(_SAMPLE_FILES / "CustomFoods_Samplefile.txt")
        assert result.block_type is BlockType.CUSTOM_FOODS
        assert len(result.custom_foods) == 1

        burger = result.custom_foods[0]
        assert burger.item_id == "Peeperburger"
        assert burger.display_name == "Peeperburger"
        assert burger.food_value == 20
        assert burger.water_value == 11
        assert burger.decay_rate_mod == 0.5
        assert len(burger.ingredients) == 3
        assert burger.force_unlock_at_start is True


class TestIntegrationAlchCustomFab:
    """Integration test: parse __Alch_NEW_CustomFAB__.txt."""

    _FILE = _REAL_MOD_EXAMPLES / "__Alch_NEW_CustomFAB__.txt"

    def test_file_exists(self) -> None:
        assert self._FILE.exists(), f"Reference file missing: {self._FILE}"

    def test_block_type(self) -> None:
        result = parse_file(self._FILE)
        assert result.block_type is BlockType.CUSTOM_FABRICATORS

    def test_one_fabricator(self) -> None:
        result = parse_file(self._FILE)
        assert len(result.custom_fabricators) == 1

    def test_fabricator_identity(self) -> None:
        result = parse_file(self._FILE)
        fab = result.custom_fabricators[0]
        assert fab.item_id == "Alch_Fab"
        assert fab.display_name == "Alchemic Fabricator"
        assert fab.model == "MoonPool"

    def test_fabricator_settings(self) -> None:
        result = parse_file(self._FILE)
        fab = result.custom_fabricators[0]
        assert fab.allowed_in_base is True
        assert fab.allowed_in_cyclops is True
        assert fab.force_unlock_at_start is False
        assert fab.unlocked_by == ["FarmingTray"]

    def test_color_tint(self) -> None:
        result = parse_file(self._FILE)
        fab = result.custom_fabricators[0]
        assert fab.color_tint == [0.1, 1.0, 0.5, 1.0]

    def test_fabricator_ingredients(self) -> None:
        result = parse_file(self._FILE)
        fab = result.custom_fabricators[0]
        assert len(fab.ingredients) == 9
        assert fab.ingredients[0] == Ingredient("AdvancedWiringKit", 1)
        assert fab.ingredients[-1] == Ingredient("Diamond", 1)

    def test_tab_count(self) -> None:
        result = parse_file(self._FILE)
        fab = result.custom_fabricators[0]
        assert len(fab.tabs) == 30

    def test_first_tab(self) -> None:
        result = parse_file(self._FILE)
        tab = result.custom_fabricators[0].tabs[0]
        assert tab.tab_id == "Alch_ComplexCompounds"
        assert tab.display_name == "COMPLEX COMPOUNDS"
        assert tab.parent_tab_path == "Alch_Fab"

    def test_nested_tab_paths(self) -> None:
        """Sub-tabs reference their parent via slash-separated paths."""
        result = parse_file(self._FILE)
        tabs = result.custom_fabricators[0].tabs
        enzymes = tabs[1]
        assert enzymes.tab_id == "Alch_Enzymes"
        assert enzymes.parent_tab_path == "Alch_Fab/Alch_ComplexCompounds"

    def test_tab_with_sprite(self) -> None:
        result = parse_file(self._FILE)
        tabs = result.custom_fabricators[0].tabs
        lab_eq = tabs[3]
        assert lab_eq.tab_id == "Alch_LabEquipment"
        assert lab_eq.sprite_item_id == "LabEquipment1"

    def test_last_tab(self) -> None:
        result = parse_file(self._FILE)
        last_tab = result.custom_fabricators[0].tabs[-1]
        assert last_tab.tab_id == "Alch_CookingFood"
        assert last_tab.parent_tab_path == "Alch_Fab/Alch_Survival"

    def test_no_nested_recipes(self) -> None:
        """This file only defines the fabricator structure, no recipes."""
        result = parse_file(self._FILE)
        fab = result.custom_fabricators[0]
        assert fab.added_recipes == []
        assert fab.alias_recipes == []

    def test_tooltip_with_special_chars(self) -> None:
        """The tooltip contains apostrophes, colons, and ellipsis."""
        result = parse_file(self._FILE)
        fab = result.custom_fabricators[0]
        assert "Alchemy" in fab.tooltip
        assert "..." in fab.tooltip


class TestIntegrationBigFilteredWater:
    """Integration test: parse BigFilteredWater.txt."""

    _FILE = _REAL_MOD_EXAMPLES / "BigFilteredWater.txt"

    def test_file_exists(self) -> None:
        assert self._FILE.exists(), f"Reference file missing: {self._FILE}"

    def test_block_type(self) -> None:
        result = parse_file(self._FILE)
        assert result.block_type is BlockType.ADDED_RECIPES

    def test_one_recipe(self) -> None:
        result = parse_file(self._FILE)
        assert len(result.added_recipes) == 1

    def test_recipe_details(self) -> None:
        result = parse_file(self._FILE)
        recipe = result.added_recipes[0]
        assert recipe.item_id == "bigfilteredwater"
        assert recipe.amount_crafted == 1
        assert recipe.path == "Fabricator/Survival/Water"
        assert recipe.unlocked_by == ["disinfectedwater"]
        assert recipe.force_unlock_at_start is False
        assert recipe.ingredients == [Ingredient("bleach", 1)]


class TestIntegrationCustomFab3:
    """Integration test: parse customfab3.txt (Seamoth Parts Fabricator)."""

    _FILE = _REAL_MOD_EXAMPLES / "customfab3.txt"

    def test_file_exists(self) -> None:
        assert self._FILE.exists(), f"Reference file missing: {self._FILE}"

    def test_block_type(self) -> None:
        result = parse_file(self._FILE)
        assert result.block_type is BlockType.CUSTOM_FABRICATORS

    def test_one_fabricator(self) -> None:
        result = parse_file(self._FILE)
        assert len(result.custom_fabricators) == 1

    def test_fabricator_identity(self) -> None:
        result = parse_file(self._FILE)
        fab = result.custom_fabricators[0]
        assert fab.item_id == "Seafab"
        assert fab.display_name == "Seamoth Parts Fabricator"
        assert fab.tooltip == "Fabricate Mechanical Parts"
        assert fab.model == "Workbench"

    def test_fabricator_settings(self) -> None:
        result = parse_file(self._FILE)
        fab = result.custom_fabricators[0]
        assert fab.force_unlock_at_start is False
        assert fab.unlocked_by == ["seamoth", "workbench"]
        assert fab.color_tint == [0.0, 0.1, 1.0, 1.0]

    def test_fabricator_ingredients(self) -> None:
        result = parse_file(self._FILE)
        fab = result.custom_fabricators[0]
        assert len(fab.ingredients) == 4
        assert fab.ingredients[0] == Ingredient("builder", 2)
        assert fab.ingredients[1] == Ingredient("wiringkit", 1)
        assert fab.ingredients[2] == Ingredient("copperwire", 1)
        assert fab.ingredients[3] == Ingredient("titaniumingot", 1)

    def test_tab_count(self) -> None:
        result = parse_file(self._FILE)
        fab = result.custom_fabricators[0]
        assert len(fab.tabs) == 5

    def test_tabs(self) -> None:
        result = parse_file(self._FILE)
        tabs = result.custom_fabricators[0].tabs
        tab_ids = [t.tab_id for t in tabs]
        assert tab_ids == ["Seapart", "Inside", "Ass", "Elc", "Mech"]

    def test_alias_recipe_count(self) -> None:
        result = parse_file(self._FILE)
        fab = result.custom_fabricators[0]
        assert len(fab.alias_recipes) == 17

    def test_first_alias_recipe(self) -> None:
        result = parse_file(self._FILE)
        seat = result.custom_fabricators[0].alias_recipes[0]
        assert seat.item_id == "seat"
        assert seat.display_name == "Seamoth Seat"
        assert seat.tooltip == "Comfortable seat for the pilot"
        assert seat.linked_item_ids == ["seat"]
        assert seat.path == "Seafab/Inside"
        assert len(seat.ingredients) == 3
        assert seat.ingredients[0] == Ingredient("fibermesh", 2)

    def test_last_alias_recipe(self) -> None:
        result = parse_file(self._FILE)
        mech = result.custom_fabricators[0].alias_recipes[-1]
        assert mech.item_id == "assemmech"
        assert mech.display_name == "Assembled Mechanical Parts"
        assert mech.path == "Seafab/Ass"
        assert len(mech.ingredients) == 3

    def test_all_recipes_traverses_fabricator(self) -> None:
        """all_recipes includes the 17 alias recipes nested in the fabricator."""
        result = parse_file(self._FILE)
        assert len(result.all_recipes) == 17
        ids = [r.item_id for r in result.all_recipes]
        assert "seat" in ids
        assert "assemmech" in ids


class TestIntegrationCustomSizes:
    """Integration test: parse customsizze.txt."""

    _FILE = _REAL_MOD_EXAMPLES / "customsizze.txt"

    def test_file_exists(self) -> None:
        assert self._FILE.exists(), f"Reference file missing: {self._FILE}"

    def test_block_type(self) -> None:
        result = parse_file(self._FILE)
        assert result.block_type is BlockType.CUSTOM_SIZES

    def test_entry_count(self) -> None:
        result = parse_file(self._FILE)
        assert len(result.custom_sizes) == 17

    def test_first_entry(self) -> None:
        result = parse_file(self._FILE)
        assert result.custom_sizes[0] == CustomSize("seat", 1, 2)

    def test_large_size(self) -> None:
        result = parse_file(self._FILE)
        assemhull = result.custom_sizes[13]
        assert assemhull == CustomSize("assemhull", 6, 3)

    def test_last_entry(self) -> None:
        result = parse_file(self._FILE)
        assert result.custom_sizes[-1] == CustomSize("assemmech", 6, 3)


# ---------------------------------------------------------------------------
# parse_text -- string-based parsing entry point
# ---------------------------------------------------------------------------


class TestParseText:
    """Tests for parse_text() -- string-based parsing entry point."""

    def test_parse_modified_recipe_from_text(self) -> None:
        text = (
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    AmountCrafted: 2;\n"
            ");\n"
        )
        pf = parse_text(text, source_path=Path("test.txt"))
        assert pf.block_type == BlockType.MODIFIED_RECIPES
        assert len(pf.modified_recipes) == 1
        assert pf.modified_recipes[0].item_id == "Titanium"
        assert pf.modified_recipes[0].amount_crafted == 2

    def test_parse_text_empty_string(self) -> None:
        pf = parse_text("", source_path=Path("empty.txt"))
        assert pf.block_type is None
        assert pf.source_path == Path("empty.txt")

    def test_parse_text_round_trip_with_serializer(self) -> None:
        """parse -> serialize -> parse_text must yield identical data."""
        text = (
            "AddedRecipes:\n"
            "(\n"
            "    ItemID: MyItem;\n"
            "    Path: Fabricator/Resources;\n"
            ");\n"
        )
        pf1 = parse_text(text, source_path=Path("test.txt"))
        serialized = serialize_file(pf1)
        pf2 = parse_text(serialized, source_path=Path("test.txt"))
        assert pf2.block_type == pf1.block_type
        assert len(pf2.added_recipes) == len(pf1.added_recipes)
        assert pf2.added_recipes[0].item_id == pf1.added_recipes[0].item_id

    def test_parse_text_invalid_raises_parse_error(self) -> None:
        with pytest.raises((ParseError, MappingError)):
            parse_text("NotABlockType:\n(\n);\n", source_path=Path("bad.txt"))

    def test_parse_text_source_path_preserved(self) -> None:
        text = "ModifiedRecipes:\n(\n    ItemID: X;\n);\n"
        pf = parse_text(text, source_path=Path("my/path.txt"))
        assert pf.source_path == Path("my/path.txt")
