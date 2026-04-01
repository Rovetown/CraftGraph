"""EasyMarkup serializer -- inverse of parser.py.

Converts in-memory data models back to valid CustomCraft3 EasyMarkup text files.
The primary contract: parse -> serialize -> parse must yield identical data models
(round-trip fidelity).

Formatting follows the conventions observed in CC3 reference files and the
official CustomCraftFormatter.cs:
  - 4-space indentation per nesting level
  - Booleans as YES / NO
  - DisplayName and Tooltip always double-quoted
  - Ingredients as inline blocks: ( ItemID: X; Required: N; )
  - Comma between entries, semicolon after the last
  - Fields at their default value are omitted for cleaner output
"""

from collections.abc import Callable
from typing import Any

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

# Type alias for the per-entry serializer function signature.
_EntrySerializer = Callable[..., str]

# Characters that must be escaped in raw EasyMarkup values.
_SPECIAL_CHARS = frozenset(':;(),#\\"')

INDENT = "    "  # 4 spaces per level


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def escape_value(value: str) -> str:
    """Escape EasyMarkup special characters in a raw string value.

    Mirrors CC3's ``EscapeSpecialCharacters()`` two-branch strategy:
    - Values containing spaces are wrapped in ``"..."`` (quote block).
    - Values without spaces get individual ``\\`` prefixes on special chars.

    This is the inverse of ``parser.unescape_value()``.
    """
    if not value:
        return value
    if " " in value:
        return f'"{value}"'
    parts: list[str] = []
    for ch in value:
        if ch in _SPECIAL_CHARS:
            parts.append("\\")
        parts.append(ch)
    return "".join(parts)


def quote_string(value: str) -> str:
    """Wrap *value* in double quotes for display-string fields.

    DisplayName and Tooltip are always quoted in CC3 output, regardless
    of whether they contain special characters.
    """
    return f'"{value}"'


# ---------------------------------------------------------------------------
# Low-level formatting helpers
# ---------------------------------------------------------------------------


def _field(key: str, value: str, indent: int) -> str:
    """Format a single ``Key: Value;`` line."""
    prefix = INDENT * indent
    return f"{prefix}{key}: {value};\n"


def _bool_str(value: bool) -> str:
    return "YES" if value else "NO"


def _csv(items: list[str]) -> str:
    return ", ".join(items)


def _float_str(value: float) -> str:
    """Format a float, dropping unnecessary trailing zeros."""
    # Use repr-style formatting then strip trailing zeros while keeping
    # at least one decimal digit.
    formatted = f"{value:g}"
    return formatted


# ---------------------------------------------------------------------------
# Ingredient serialization
# ---------------------------------------------------------------------------


def _serialize_ingredient(ing: Ingredient, indent: int, *, is_last: bool) -> str:
    """Serialize a single ingredient as an inline block.

    Format: ``( ItemID: X; Required: N; ),`` (or ``;`` if last).
    """
    prefix = INDENT * indent
    end_char = ";" if is_last else ","
    parts = [f"( ItemID: {escape_value(ing.item_id)};"]
    if ing.required != 1:
        parts.append(f" Required: {ing.required};")
    else:
        parts.append(f" Required: {ing.required};")
    parts.append(f" ){end_char}")
    return f"{prefix}{''.join(parts)}\n"


def _serialize_ingredients(ingredients: list[Ingredient], indent: int) -> str:
    """Serialize an ``Ingredients:`` block with its nested entries."""
    if not ingredients:
        return ""
    prefix = INDENT * indent
    lines = [f"{prefix}Ingredients:\n"]
    for i, ing in enumerate(ingredients):
        is_last = i == len(ingredients) - 1
        lines.append(_serialize_ingredient(ing, indent, is_last=is_last))
    return "".join(lines)


# ---------------------------------------------------------------------------
# Shared field emitters (avoid repeating field logic across recipe types)
# ---------------------------------------------------------------------------


def _emit_modified_fields(recipe: ModifiedRecipe, indent: int) -> list[str]:
    """Emit the fields common to all ModifiedRecipe-derived types."""
    lines: list[str] = []
    lines.append(_field("ItemID", escape_value(recipe.item_id), indent))
    if recipe.amount_crafted != 1:
        lines.append(_field("AmountCrafted", str(recipe.amount_crafted), indent))
    if recipe.ingredients:
        lines.append(_serialize_ingredients(recipe.ingredients, indent))
    if recipe.linked_item_ids:
        lines.append(_field("LinkedItemIDs", _csv(recipe.linked_item_ids), indent))
    if recipe.unlocks:
        lines.append(_field("Unlocks", _csv(recipe.unlocks), indent))
    if recipe.force_unlock_at_start is not None:
        lines.append(_field("ForceUnlockAtStart", _bool_str(recipe.force_unlock_at_start), indent))
    if recipe.unlocked_by:
        lines.append(_field("UnlockedBy", _csv(recipe.unlocked_by), indent))
    return lines


def _emit_added_fields(recipe: AddedRecipe, indent: int) -> list[str]:
    """Emit fields specific to AddedRecipe (path, PDA placement)."""
    lines: list[str] = []
    if recipe.path:
        lines.append(_field("Path", recipe.path, indent))
    if recipe.pda_group is not None:
        lines.append(_field("PdaGroup", recipe.pda_group, indent))
    if recipe.pda_category is not None:
        lines.append(_field("PdaCategory", recipe.pda_category, indent))
    return lines


def _emit_alias_fields(recipe: AliasRecipe, indent: int) -> list[str]:
    """Emit fields specific to AliasRecipe (display, identity)."""
    lines: list[str] = []
    if recipe.display_name:
        lines.append(_field("DisplayName", quote_string(recipe.display_name), indent))
    if recipe.tooltip:
        lines.append(_field("Tooltip", quote_string(recipe.tooltip), indent))
    if recipe.functional_id is not None:
        lines.append(_field("FunctionalID", recipe.functional_id, indent))
    if recipe.sprite_item_id is not None:
        lines.append(_field("SpriteItemID", recipe.sprite_item_id, indent))
    return lines


def _emit_custom_food_fields(food: CustomFood, indent: int) -> list[str]:
    """Emit fields specific to CustomFood (nutrition stats)."""
    lines: list[str] = []
    if food.food_value != 0:
        lines.append(_field("FoodValue", str(food.food_value), indent))
    if food.water_value != 0:
        lines.append(_field("WaterValue", str(food.water_value), indent))
    if food.oxygen_value != 0:
        lines.append(_field("OxygenValue", str(food.oxygen_value), indent))
    if food.health_value != 0:
        lines.append(_field("HealthValue", str(food.health_value), indent))
    if food.decay_rate_mod != 0.0:
        lines.append(_field("DecayRateMod", _float_str(food.decay_rate_mod), indent))
    if food.food_type is not None:
        lines.append(_field("FoodType", food.food_type, indent))
    if food.use_drink_sound is not None:
        lines.append(_field("UseDrinkSound", _bool_str(food.use_drink_sound), indent))
    return lines


# ---------------------------------------------------------------------------
# Per-type entry serializers
# ---------------------------------------------------------------------------


def _serialize_modified_recipe(recipe: ModifiedRecipe, indent: int, *, is_last: bool) -> str:
    prefix = INDENT * indent
    end_char = ";" if is_last else ","
    lines = [f"{prefix}(\n"]
    lines.extend(_emit_modified_fields(recipe, indent + 1))
    lines.append(f"{prefix}){end_char}\n")
    return "".join(lines)


def _serialize_added_recipe(recipe: AddedRecipe, indent: int, *, is_last: bool) -> str:
    prefix = INDENT * indent
    end_char = ";" if is_last else ","
    lines = [f"{prefix}(\n"]
    lines.extend(_emit_modified_fields(recipe, indent + 1))
    lines.extend(_emit_added_fields(recipe, indent + 1))
    lines.append(f"{prefix}){end_char}\n")
    return "".join(lines)


def _serialize_alias_recipe(recipe: AliasRecipe, indent: int, *, is_last: bool) -> str:
    prefix = INDENT * indent
    end_char = ";" if is_last else ","
    lines = [f"{prefix}(\n"]
    # Alias field order: identity fields first, then base fields
    inner = indent + 1
    lines.append(_field("ItemID", escape_value(recipe.item_id), inner))
    if recipe.display_name:
        lines.append(_field("DisplayName", quote_string(recipe.display_name), inner))
    if recipe.tooltip:
        lines.append(_field("Tooltip", quote_string(recipe.tooltip), inner))
    if recipe.amount_crafted != 1:
        lines.append(_field("AmountCrafted", str(recipe.amount_crafted), inner))
    if recipe.ingredients:
        lines.append(_serialize_ingredients(recipe.ingredients, inner))
    if recipe.linked_item_ids:
        lines.append(_field("LinkedItemIDs", _csv(recipe.linked_item_ids), inner))
    if recipe.unlocks:
        lines.append(_field("Unlocks", _csv(recipe.unlocks), inner))
    if recipe.force_unlock_at_start is not None:
        lines.append(_field("ForceUnlockAtStart", _bool_str(recipe.force_unlock_at_start), inner))
    if recipe.unlocked_by:
        lines.append(_field("UnlockedBy", _csv(recipe.unlocked_by), inner))
    if recipe.path:
        lines.append(_field("Path", recipe.path, inner))
    if recipe.pda_group is not None:
        lines.append(_field("PdaGroup", recipe.pda_group, inner))
    if recipe.pda_category is not None:
        lines.append(_field("PdaCategory", recipe.pda_category, inner))
    if recipe.functional_id is not None:
        lines.append(_field("FunctionalID", recipe.functional_id, inner))
    if recipe.sprite_item_id is not None:
        lines.append(_field("SpriteItemID", recipe.sprite_item_id, inner))
    lines.append(f"{prefix}){end_char}\n")
    return "".join(lines)


def _serialize_custom_food(food: CustomFood, indent: int, *, is_last: bool) -> str:
    prefix = INDENT * indent
    end_char = ";" if is_last else ","
    lines = [f"{prefix}(\n"]
    inner = indent + 1
    # Same order as alias, then food-specific fields
    lines.append(_field("ItemID", escape_value(food.item_id), inner))
    if food.display_name:
        lines.append(_field("DisplayName", quote_string(food.display_name), inner))
    if food.tooltip:
        lines.append(_field("Tooltip", quote_string(food.tooltip), inner))
    if food.amount_crafted != 1:
        lines.append(_field("AmountCrafted", str(food.amount_crafted), inner))
    if food.ingredients:
        lines.append(_serialize_ingredients(food.ingredients, inner))
    if food.linked_item_ids:
        lines.append(_field("LinkedItemIDs", _csv(food.linked_item_ids), inner))
    if food.unlocks:
        lines.append(_field("Unlocks", _csv(food.unlocks), inner))
    if food.force_unlock_at_start is not None:
        lines.append(_field("ForceUnlockAtStart", _bool_str(food.force_unlock_at_start), inner))
    if food.unlocked_by:
        lines.append(_field("UnlockedBy", _csv(food.unlocked_by), inner))
    if food.path:
        lines.append(_field("Path", food.path, inner))
    if food.pda_group is not None:
        lines.append(_field("PdaGroup", food.pda_group, inner))
    if food.pda_category is not None:
        lines.append(_field("PdaCategory", food.pda_category, inner))
    if food.functional_id is not None:
        lines.append(_field("FunctionalID", food.functional_id, inner))
    if food.sprite_item_id is not None:
        lines.append(_field("SpriteItemID", food.sprite_item_id, inner))
    lines.extend(_emit_custom_food_fields(food, inner))
    lines.append(f"{prefix}){end_char}\n")
    return "".join(lines)


def _serialize_crafting_tab(tab: CraftingTab, indent: int, *, is_last: bool) -> str:
    prefix = INDENT * indent
    end_char = ";" if is_last else ","
    lines = [f"{prefix}(\n"]
    inner = indent + 1
    lines.append(_field("TabID", escape_value(tab.tab_id), inner))
    if tab.display_name:
        lines.append(_field("DisplayName", quote_string(tab.display_name), inner))
    if tab.sprite_item_id is not None:
        lines.append(_field("SpriteItemID", tab.sprite_item_id, inner))
    if tab.parent_tab_path:
        lines.append(_field("ParentTabPath", tab.parent_tab_path, inner))
    lines.append(f"{prefix}){end_char}\n")
    return "".join(lines)


def _serialize_moved_recipe(recipe: MovedRecipe, indent: int, *, is_last: bool) -> str:
    prefix = INDENT * indent
    end_char = ";" if is_last else ","
    lines = [f"{prefix}(\n"]
    inner = indent + 1
    lines.append(_field("ItemID", escape_value(recipe.item_id), inner))
    if recipe.old_path is not None:
        lines.append(_field("OldPath", recipe.old_path, inner))
    if recipe.new_path is not None:
        lines.append(_field("NewPath", recipe.new_path, inner))
    if recipe.copied:
        lines.append(_field("Copied", _bool_str(recipe.copied), inner))
    if recipe.hidden:
        lines.append(_field("Hidden", _bool_str(recipe.hidden), inner))
    lines.append(f"{prefix}){end_char}\n")
    return "".join(lines)


def _serialize_custom_size(size: CustomSize, indent: int, *, is_last: bool) -> str:
    prefix = INDENT * indent
    end_char = ";" if is_last else ","
    lines = [f"{prefix}(\n"]
    inner = indent + 1
    lines.append(_field("ItemID", escape_value(size.item_id), inner))
    # Always write Width and Height for CustomSize, even at defaults
    lines.append(_field("Width", str(size.width), inner))
    lines.append(_field("Height", str(size.height), inner))
    lines.append(f"{prefix}){end_char}\n")
    return "".join(lines)


def _serialize_custom_bio_fuel(fuel: CustomBioFuel, indent: int, *, is_last: bool) -> str:
    prefix = INDENT * indent
    end_char = ";" if is_last else ","
    lines = [f"{prefix}(\n"]
    inner = indent + 1
    lines.append(_field("ItemID", escape_value(fuel.item_id), inner))
    if fuel.energy != 0.0:
        lines.append(_field("Energy", _float_str(fuel.energy), inner))
    lines.append(f"{prefix}){end_char}\n")
    return "".join(lines)


def _serialize_custom_fragment_count(
    frag: CustomFragmentCount, indent: int, *, is_last: bool
) -> str:
    prefix = INDENT * indent
    end_char = ";" if is_last else ","
    lines = [f"{prefix}(\n"]
    inner = indent + 1
    lines.append(_field("ItemID", escape_value(frag.item_id), inner))
    if frag.fragments_to_scan != 1:
        lines.append(_field("FragmentsToScan", str(frag.fragments_to_scan), inner))
    lines.append(f"{prefix}){end_char}\n")
    return "".join(lines)


# ---------------------------------------------------------------------------
# CustomFabricator (complex: own fields + nested sub-entry blocks)
# ---------------------------------------------------------------------------


def _serialize_nested_block(
    block_label: str,
    items: list[Any],
    serializer: _EntrySerializer,
    indent: int,
) -> str:
    """Serialize a nested sub-entry block inside a CustomFabricator."""
    if not items:
        return ""
    prefix = INDENT * indent
    lines = [f"{prefix}{block_label}:\n"]
    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        lines.append(serializer(item, indent, is_last=is_last))
    return "".join(lines)


def _serialize_custom_fabricator(fab: CustomFabricator, indent: int, *, is_last: bool) -> str:
    prefix = INDENT * indent
    end_char = ";" if is_last else ","
    lines = [f"{prefix}(\n"]
    inner = indent + 1

    # Own scalar fields
    lines.append(_field("ItemID", escape_value(fab.item_id), inner))
    if fab.display_name:
        lines.append(_field("DisplayName", quote_string(fab.display_name), inner))
    if fab.tooltip:
        lines.append(_field("Tooltip", quote_string(fab.tooltip), inner))
    if fab.model != "Fabricator":
        lines.append(_field("Model", fab.model, inner))
    if fab.color_tint:
        tint_str = ", ".join(_float_str(v) for v in fab.color_tint)
        lines.append(_field("ColorTint", tint_str, inner))
    if not fab.allowed_in_base:
        lines.append(_field("AllowedInBase", _bool_str(fab.allowed_in_base), inner))
    if not fab.allowed_in_cyclops:
        lines.append(_field("AllowedInCyclops", _bool_str(fab.allowed_in_cyclops), inner))
    if fab.ingredients:
        lines.append(_serialize_ingredients(fab.ingredients, inner))
    if fab.pda_group is not None:
        lines.append(_field("PdaGroup", fab.pda_group, inner))
    if fab.pda_category is not None:
        lines.append(_field("PdaCategory", fab.pda_category, inner))
    if fab.force_unlock_at_start is not None:
        lines.append(_field("ForceUnlockAtStart", _bool_str(fab.force_unlock_at_start), inner))
    if fab.unlocked_by:
        lines.append(_field("UnlockedBy", _csv(fab.unlocked_by), inner))

    # Nested sub-entry blocks
    lines.append(
        _serialize_nested_block("CustomCraftingTabs", fab.tabs, _serialize_crafting_tab, inner)
    )
    lines.append(
        _serialize_nested_block("AddedRecipes", fab.added_recipes, _serialize_added_recipe, inner)
    )
    lines.append(
        _serialize_nested_block("AliasRecipes", fab.alias_recipes, _serialize_alias_recipe, inner)
    )
    lines.append(
        _serialize_nested_block("MovedRecipes", fab.moved_recipes, _serialize_moved_recipe, inner)
    )
    lines.append(
        _serialize_nested_block("CustomFoods", fab.custom_foods, _serialize_custom_food, inner)
    )

    lines.append(f"{prefix}){end_char}\n")
    return "".join(lines)


# ---------------------------------------------------------------------------
# Top-level block serializers
# ---------------------------------------------------------------------------

# Maps each BlockType to (list attribute name on ParsedFile, entry serializer function).
_BLOCK_DISPATCH: dict[BlockType, tuple[str, _EntrySerializer]] = {
    BlockType.MODIFIED_RECIPES: ("modified_recipes", _serialize_modified_recipe),
    BlockType.ADDED_RECIPES: ("added_recipes", _serialize_added_recipe),
    BlockType.ALIAS_RECIPES: ("alias_recipes", _serialize_alias_recipe),
    BlockType.CUSTOM_FOODS: ("custom_foods", _serialize_custom_food),
    BlockType.CUSTOM_CRAFTING_TABS: ("crafting_tabs", _serialize_crafting_tab),
    BlockType.CUSTOM_FABRICATORS: ("custom_fabricators", _serialize_custom_fabricator),
    BlockType.MOVED_RECIPES: ("moved_recipes", _serialize_moved_recipe),
    BlockType.CUSTOM_SIZES: ("custom_sizes", _serialize_custom_size),
    BlockType.CUSTOM_BIO_FUELS: ("custom_bio_fuels", _serialize_custom_bio_fuel),
    BlockType.CUSTOM_FRAGMENT_COUNTS: ("custom_fragment_counts", _serialize_custom_fragment_count),
}


def _serialize_entries(block_type: BlockType, entries: list[Any]) -> str:
    """Serialize a top-level block: header + entry list."""
    if not entries:
        return ""

    serializer = _BLOCK_DISPATCH[block_type][1]
    lines = [f"{block_type.value}:\n"]
    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        lines.append(serializer(entry, 0, is_last=is_last))
    return "".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def serialize_file(parsed_file: ParsedFile, *, line_ending: str = "\n") -> str:
    """Convert a ``ParsedFile`` back to EasyMarkup text.

    Returns the full file content as a string, ready to be written to disk.
    If the ``ParsedFile`` has no block type or no entries, returns an empty string.

    Args:
        parsed_file: The parsed data model to serialize.
        line_ending: Line ending to use in the output.  Defaults to ``"\\n"``
            (Python convention).  Pass ``"\\r\\n"`` for CC3-native output
            matching ``PrettyPrint()``.
    """
    if parsed_file.block_type is None:
        return ""

    attr_name = _BLOCK_DISPATCH[parsed_file.block_type][0]
    entries = getattr(parsed_file, attr_name)

    if not entries:
        return ""

    text = _serialize_entries(parsed_file.block_type, entries)
    if line_ending != "\n":
        text = text.replace("\n", line_ending)
    return text
