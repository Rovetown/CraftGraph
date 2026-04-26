"""CustomCraft3 EasyMarkup file parser.

Implements a three-phase parsing architecture modeled after CC3's EasyMarkup library:

Phase 1 -- clean_value():
    Character-by-character scan that strips whitespace and comments while
    preserving escape sequences (\\X) and quoted strings ("...") verbatim.
    Produces a dense token stream like ``Key:Value;``.

Phase 2 -- unescape_value():
    Resolves escape sequences and strips quote delimiters from a cleaned
    value segment, producing the final plain-text value.

Phase 3 -- parse_blocks():
    Recursive descent parser that takes the cleaned output from Phase 1
    and produces a structured ``ParsedBlock`` containing ``EntryBlock``
    objects. Handles nested blocks (e.g. Ingredients inside recipes,
    recipes inside CustomFabricators).

Phase 4 -- entry mapping (resolve_block_type, map_* functions):
    Converts generic ``EntryBlock`` objects into typed data model instances
    (``ModifiedRecipe``, ``AddedRecipe``, ``CustomFabricator``, etc.).
    Handles field unescaping, type coercion (int/float/bool), CSV splitting,
    and recursive mapping of nested sub-entries.

The 8 special characters in EasyMarkup:
    :  key delimiter        ;  value delimiter
    (  begin complex value  )  end complex value
    ,  list item splitter   #  comment block delimiter
    \\  escape character     "  literal string block
"""

import contextlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from craftgraph.config import get_config
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

logger = logging.getLogger(__name__)

# -- Special characters (mirrors EmProperty.cs constants) --------------------

SPCHAR_KEY_DELIM = ":"
SPCHAR_VALUE_DELIM = ";"
SPCHAR_BEGIN_COMPLEX = "("
SPCHAR_FINISH_COMPLEX = ")"
SPCHAR_LIST_SPLITTER = ","
SPCHAR_COMMENT = "#"
SPCHAR_QUOTE = '"'
SPCHAR_ESCAPE = "\\"

_WHITESPACE = frozenset(" \t\r\n")


# -- Phase 1: clean_value ---------------------------------------------------


def clean_value(raw: str) -> str:
    """Strip whitespace and comments from raw EasyMarkup text.

    Mirrors the ``CleanValue()`` method in CC3's ``EmProperty.cs``.

    - ALL whitespace (spaces, tabs, CR, LF) is removed unless inside
      a quoted string or immediately after an escape character.
    - Comments delimited by paired ``#`` characters are removed entirely.
    - Escape sequences (``\\`` + next char) pass through unchanged.
    - Quoted strings (``"..."`` including delimiters) pass through unchanged,
      preserving internal whitespace.

    Returns the cleaned string ready for Phase 2 parsing.
    """
    result: list[str] = []
    i = 0
    length = len(raw)

    while i < length:
        ch = raw[i]

        if ch in _WHITESPACE:
            # Skip all consecutive whitespace (greedy, like C# TrimStart)
            i += 1
            while i < length and raw[i] in _WHITESPACE:
                i += 1

        elif ch == SPCHAR_COMMENT:
            # Discard opening # and everything until closing # (or EOF)
            i += 1
            while i < length and raw[i] != SPCHAR_COMMENT:
                i += 1
            if i < length:
                i += 1  # skip closing #

        elif ch == SPCHAR_ESCAPE:
            # Emit the backslash and the following character as-is
            result.append(ch)
            i += 1
            if i < length:
                result.append(raw[i])
                i += 1

        elif ch == SPCHAR_QUOTE:
            # Emit opening quote and all chars until closing quote
            result.append(ch)
            i += 1
            while i < length and raw[i] != SPCHAR_QUOTE:
                result.append(raw[i])
                i += 1
            if i < length:
                result.append(raw[i])  # closing quote
                i += 1

        else:
            result.append(ch)
            i += 1

    return "".join(result)


# -- Phase 2: unescape_value ------------------------------------------------


def unescape_value(cleaned: str) -> str:
    """Resolve escape sequences and strip quote delimiters from a cleaned value.

    Mirrors the ``ReadUntilDelimiter()`` escape/quote handling in CC3's
    ``EmProperty.cs``.

    - ``\\X`` becomes literal ``X`` (the backslash is consumed).
    - ``"..."`` becomes the content between the quotes (quotes stripped).
    - All other characters pass through as-is.

    Operates on already-cleaned input (output of ``clean_value``).
    """
    result: list[str] = []
    i = 0
    length = len(cleaned)

    while i < length:
        ch = cleaned[i]

        if ch == SPCHAR_ESCAPE:
            i += 1
            if i < length:
                result.append(cleaned[i])
                i += 1
            else:
                # Trailing backslash with nothing after
                result.append(SPCHAR_ESCAPE)

        elif ch == SPCHAR_QUOTE:
            i += 1  # skip opening quote
            while i < length and cleaned[i] != SPCHAR_QUOTE:
                result.append(cleaned[i])
                i += 1
            if i < length:
                i += 1  # skip closing quote

        else:
            result.append(ch)
            i += 1

    return "".join(result)


# -- Phase 3: block-level parser ---------------------------------------------


class ParseError(Exception):
    """Raised when EasyMarkup structural parsing fails."""


@dataclass
class EntryBlock:
    """A single parsed entry (one recipe, one custom size, etc.).

    Fields are stored with lowercased keys for case-insensitive lookup.
    Simple values remain as raw cleaned strings (still containing escape
    sequences and quote delimiters -- call unescape_value() to resolve).
    Nested entry lists (like Ingredients) are stored separately.
    """

    fields: dict[str, str] = field(default_factory=dict)
    sub_entries: dict[str, list[EntryBlock]] = field(default_factory=dict)


@dataclass
class ParsedBlock:
    """A top-level block parsed from cleaned EasyMarkup text.

    block_type is the raw keyword (e.g. "ModifiedRecipes") before the
    first colon. entries contains each ``(...)`` child as an EntryBlock.
    """

    block_type: str
    entries: list[EntryBlock] = field(default_factory=list)


class _BlockParser:
    """Recursive descent parser for cleaned EasyMarkup text.

    Operates on the output of clean_value() -- a dense string with no
    whitespace or comments, but escape sequences and quoted strings intact.
    """

    def __init__(self, text: str) -> None:
        self._text = text
        self._pos = 0

    # -- cursor helpers --------------------------------------------------------

    def _at_end(self) -> bool:
        return self._pos >= len(self._text)

    def _peek(self) -> str:
        if self._at_end():
            return ""
        return self._text[self._pos]

    def _advance(self) -> str:
        ch = self._text[self._pos]
        self._pos += 1
        return ch

    def _skip_if(self, ch: str) -> bool:
        """Consume the next character if it matches, return whether it did."""
        if self._peek() == ch:
            self._advance()
            return True
        return False

    def _read_until(self, *terminators: str) -> str:
        """Read characters until an unescaped, unquoted terminator is found.

        Escape sequences (\\X) and quoted strings ("...") are passed through
        without inspecting their contents for terminators.
        """
        result: list[str] = []
        while not self._at_end():
            ch = self._peek()
            if ch == SPCHAR_ESCAPE:
                result.append(self._advance())  # backslash
                if not self._at_end():
                    result.append(self._advance())  # escaped char
            elif ch == SPCHAR_QUOTE:
                result.append(self._advance())  # opening quote
                while not self._at_end() and self._peek() != SPCHAR_QUOTE:
                    result.append(self._advance())
                if not self._at_end():
                    result.append(self._advance())  # closing quote
            elif ch in terminators:
                break
            else:
                result.append(self._advance())
        return "".join(result)

    # -- grammar rules ---------------------------------------------------------

    def parse(self) -> ParsedBlock:
        """Parse the full cleaned text into a ParsedBlock."""
        block_type = self._read_until(SPCHAR_KEY_DELIM)
        if not block_type:
            raise ParseError("Empty input: no block type found")
        if not self._skip_if(SPCHAR_KEY_DELIM):
            raise ParseError(
                f"Expected ':' after block type '{block_type}' at position {self._pos}"
            )
        entries = self._parse_entry_list()
        return ParsedBlock(block_type=block_type, entries=entries)

    def _parse_entry_list(self) -> list[EntryBlock]:
        """Parse ``(entry),(entry),...,(entry);`` into a list of EntryBlocks."""
        entries: list[EntryBlock] = []
        while self._peek() == SPCHAR_BEGIN_COMPLEX:
            self._advance()  # consume '('
            entry = self._parse_entry()
            if not self._skip_if(SPCHAR_FINISH_COMPLEX):
                raise ParseError(f"Expected ')' to close entry at position {self._pos}")
            entries.append(entry)
            if self._peek() == SPCHAR_LIST_SPLITTER:
                self._advance()  # comma between entries
            elif self._peek() == SPCHAR_VALUE_DELIM:
                self._advance()  # semicolon terminates the list
                break
            # else: no separator (EOF or parent ')') -- just stop
        return entries

    def _parse_entry(self) -> EntryBlock:
        """Parse key-value fields inside a single ``(...)`` block."""
        entry = EntryBlock()
        while not self._at_end() and self._peek() != SPCHAR_FINISH_COMPLEX:
            key = self._read_until(SPCHAR_KEY_DELIM, SPCHAR_FINISH_COMPLEX)
            if not key or self._peek() != SPCHAR_KEY_DELIM:
                break
            self._advance()  # consume ':'

            key_lower = key.lower()

            if self._peek() == SPCHAR_BEGIN_COMPLEX:
                # Value is a nested entry list: Ingredients:(...),(...);
                entry.sub_entries[key_lower] = self._parse_entry_list()
            else:
                # Simple value: read until ';' or parent ')'
                value = self._read_until(SPCHAR_VALUE_DELIM, SPCHAR_FINISH_COMPLEX)
                self._skip_if(SPCHAR_VALUE_DELIM)
                entry.fields[key_lower] = value

        return entry


def parse_blocks(cleaned: str) -> ParsedBlock:
    """Parse cleaned EasyMarkup text into a structured ParsedBlock.

    Takes the output of clean_value() and produces a block type name plus
    a list of EntryBlock objects, each containing key-value fields and
    optional nested sub-entry lists.

    Raises ParseError if the text cannot be parsed.
    """
    if not cleaned:
        raise ParseError("Empty input")
    parser = _BlockParser(cleaned)
    return parser.parse()


# -- Phase 4: entry mapping ---------------------------------------------------


class MappingError(Exception):
    """Raised when an EntryBlock cannot be mapped to a data model."""


# -- Block type resolution -----------------------------------------------------

_BLOCK_TYPE_LOOKUP: dict[str, BlockType] = {bt.value.lower(): bt for bt in BlockType}


def resolve_block_type(raw_type: str) -> BlockType:
    """Resolve a raw block-type string to a ``BlockType`` enum member.

    Matching is case-insensitive. Raises ``MappingError`` for unknown types.
    """
    key = raw_type.lower()
    if key not in _BLOCK_TYPE_LOOKUP:
        raise MappingError(f"Unknown block type: '{raw_type}'")
    return _BLOCK_TYPE_LOOKUP[key]


# -- Private field helpers -----------------------------------------------------


def _get_field(entry: EntryBlock, key: str) -> str | None:
    """Return an unescaped field value, or ``None`` if the key is absent."""
    raw = entry.fields.get(key)
    if raw is None:
        return None
    return unescape_value(raw)


def _require_field(entry: EntryBlock, key: str) -> str:
    """Return an unescaped field value, raising ``MappingError`` if absent."""
    value = _get_field(entry, key)
    if value is None:
        raise MappingError(f"Required field '{key}' missing from entry")
    return value


def _parse_bool(value: str) -> bool:
    """Convert a CC3 boolean string (YES/NO/TRUE/FALSE) to ``bool``."""
    return value.strip().upper() in ("YES", "TRUE", "1")


def _get_optional_bool(entry: EntryBlock, key: str) -> bool | None:
    """Return a boolean field value, or ``None`` if the key is absent."""
    value = _get_field(entry, key)
    if value is None:
        return None
    return _parse_bool(value)


def _get_bool(entry: EntryBlock, key: str, *, default: bool) -> bool:
    """Return a boolean field value with a fallback default."""
    value = _get_field(entry, key)
    if value is None:
        return default
    return _parse_bool(value)


def _get_int(entry: EntryBlock, key: str, *, default: int) -> int:
    """Return an integer field value with a fallback default."""
    value = _get_field(entry, key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float(entry: EntryBlock, key: str, *, default: float) -> float:
    """Return a float field value with a fallback default."""
    value = _get_field(entry, key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _split_csv(value: str) -> list[str]:
    """Split a comma-separated value string into a list of non-empty items."""
    if not value:
        return []
    return [item for item in value.split(",") if item]


def _get_csv(entry: EntryBlock, key: str) -> list[str]:
    """Return a comma-separated field as a list of strings."""
    value = _get_field(entry, key)
    if value is None:
        return []
    return _split_csv(value)


def _map_ingredients(entry: EntryBlock) -> list[Ingredient]:
    """Map the ``ingredients`` sub-entry list to ``Ingredient`` objects."""
    sub = entry.sub_entries.get("ingredients", [])
    return [
        Ingredient(
            item_id=_require_field(ing, "itemid"),
            required=_get_int(ing, "required", default=1),
        )
        for ing in sub
    ]


# -- Per-type mappers ----------------------------------------------------------


def map_modified_recipe(entry: EntryBlock) -> ModifiedRecipe:
    """Map an ``EntryBlock`` to a ``ModifiedRecipe``."""
    return ModifiedRecipe(
        item_id=_require_field(entry, "itemid"),
        amount_crafted=_get_int(entry, "amountcrafted", default=1),
        ingredients=_map_ingredients(entry),
        linked_item_ids=_get_csv(entry, "linkeditemids"),
        unlocks=_get_csv(entry, "unlocks"),
        force_unlock_at_start=_get_optional_bool(entry, "forceunlockatstart"),
        unlocked_by=_get_csv(entry, "unlockedby"),
    )


def map_added_recipe(entry: EntryBlock) -> AddedRecipe:
    """Map an ``EntryBlock`` to an ``AddedRecipe``."""
    return AddedRecipe(
        item_id=_require_field(entry, "itemid"),
        amount_crafted=_get_int(entry, "amountcrafted", default=1),
        ingredients=_map_ingredients(entry),
        linked_item_ids=_get_csv(entry, "linkeditemids"),
        unlocks=_get_csv(entry, "unlocks"),
        force_unlock_at_start=_get_optional_bool(entry, "forceunlockatstart"),
        unlocked_by=_get_csv(entry, "unlockedby"),
        path=_get_field(entry, "path") or "",
        pda_group=_get_field(entry, "pdagroup"),
        pda_category=_get_field(entry, "pdacategory"),
    )


def map_alias_recipe(entry: EntryBlock) -> AliasRecipe:
    """Map an ``EntryBlock`` to an ``AliasRecipe``."""
    return AliasRecipe(
        item_id=_require_field(entry, "itemid"),
        amount_crafted=_get_int(entry, "amountcrafted", default=1),
        ingredients=_map_ingredients(entry),
        linked_item_ids=_get_csv(entry, "linkeditemids"),
        unlocks=_get_csv(entry, "unlocks"),
        force_unlock_at_start=_get_optional_bool(entry, "forceunlockatstart"),
        unlocked_by=_get_csv(entry, "unlockedby"),
        path=_get_field(entry, "path") or "",
        pda_group=_get_field(entry, "pdagroup"),
        pda_category=_get_field(entry, "pdacategory"),
        display_name=_get_field(entry, "displayname") or "",
        tooltip=_get_field(entry, "tooltip") or "",
        functional_id=_get_field(entry, "functionalid"),
        sprite_item_id=_get_field(entry, "spriteitemid"),
    )


def map_custom_food(entry: EntryBlock) -> CustomFood:
    """Map an ``EntryBlock`` to a ``CustomFood``."""
    return CustomFood(
        item_id=_require_field(entry, "itemid"),
        amount_crafted=_get_int(entry, "amountcrafted", default=1),
        ingredients=_map_ingredients(entry),
        linked_item_ids=_get_csv(entry, "linkeditemids"),
        unlocks=_get_csv(entry, "unlocks"),
        force_unlock_at_start=_get_optional_bool(entry, "forceunlockatstart"),
        unlocked_by=_get_csv(entry, "unlockedby"),
        path=_get_field(entry, "path") or "",
        pda_group=_get_field(entry, "pdagroup"),
        pda_category=_get_field(entry, "pdacategory"),
        display_name=_get_field(entry, "displayname") or "",
        tooltip=_get_field(entry, "tooltip") or "",
        functional_id=_get_field(entry, "functionalid"),
        sprite_item_id=_get_field(entry, "spriteitemid"),
        food_value=_get_int(entry, "foodvalue", default=0),
        water_value=_get_int(entry, "watervalue", default=0),
        oxygen_value=_get_int(entry, "oxygenvalue", default=0),
        health_value=_get_int(entry, "healthvalue", default=0),
        decay_rate_mod=_get_float(entry, "decayratemod", default=0.0),
        food_type=_get_field(entry, "foodtype"),
        use_drink_sound=_get_optional_bool(entry, "usedrinksound"),
    )


def map_crafting_tab(entry: EntryBlock) -> CraftingTab:
    """Map an ``EntryBlock`` to a ``CraftingTab``."""
    return CraftingTab(
        tab_id=_require_field(entry, "tabid"),
        display_name=_get_field(entry, "displayname") or "",
        sprite_item_id=_get_field(entry, "spriteitemid"),
        parent_tab_path=_get_field(entry, "parenttabpath") or "",
    )


def map_moved_recipe(entry: EntryBlock) -> MovedRecipe:
    """Map an ``EntryBlock`` to a ``MovedRecipe``."""
    return MovedRecipe(
        item_id=_require_field(entry, "itemid"),
        old_path=_get_field(entry, "oldpath"),
        new_path=_get_field(entry, "newpath"),
        copied=_get_bool(entry, "copied", default=False),
        hidden=_get_bool(entry, "hidden", default=False),
    )


def map_custom_size(entry: EntryBlock) -> CustomSize:
    """Map an ``EntryBlock`` to a ``CustomSize``."""
    return CustomSize(
        item_id=_require_field(entry, "itemid"),
        width=_get_int(entry, "width", default=1),
        height=_get_int(entry, "height", default=1),
    )


def map_custom_bio_fuel(entry: EntryBlock) -> CustomBioFuel:
    """Map an ``EntryBlock`` to a ``CustomBioFuel``."""
    return CustomBioFuel(
        item_id=_require_field(entry, "itemid"),
        energy=_get_float(entry, "energy", default=0.0),
    )


def map_custom_fragment_count(entry: EntryBlock) -> CustomFragmentCount:
    """Map an ``EntryBlock`` to a ``CustomFragmentCount``."""
    return CustomFragmentCount(
        item_id=_require_field(entry, "itemid"),
        fragments_to_scan=_get_int(entry, "fragmentstoscan", default=1),
    )


def map_custom_fabricator(entry: EntryBlock) -> CustomFabricator:
    """Map an ``EntryBlock`` to a ``CustomFabricator``.

    Recursively maps nested sub-entries (tabs, recipes, moved recipes,
    custom foods) using the appropriate per-type mapper.
    """
    tint_raw = _get_field(entry, "colortint")
    color_tint: list[float] = []
    if tint_raw:
        for part in tint_raw.split(","):
            with contextlib.suppress(ValueError):
                color_tint.append(float(part))

    return CustomFabricator(
        item_id=_require_field(entry, "itemid"),
        display_name=_get_field(entry, "displayname") or "",
        tooltip=_get_field(entry, "tooltip") or "",
        model=_get_field(entry, "model") or "Fabricator",
        color_tint=color_tint,
        allowed_in_base=_get_bool(entry, "allowedinbase", default=True),
        allowed_in_cyclops=_get_bool(entry, "allowedincyclops", default=True),
        ingredients=_map_ingredients(entry),
        pda_group=_get_field(entry, "pdagroup"),
        pda_category=_get_field(entry, "pdacategory"),
        force_unlock_at_start=_get_optional_bool(entry, "forceunlockatstart"),
        unlocked_by=_get_csv(entry, "unlockedby"),
        tabs=[map_crafting_tab(e) for e in entry.sub_entries.get("customcraftingtabs", [])],
        added_recipes=[map_added_recipe(e) for e in entry.sub_entries.get("addedrecipes", [])],
        alias_recipes=[map_alias_recipe(e) for e in entry.sub_entries.get("aliasrecipes", [])],
        moved_recipes=[map_moved_recipe(e) for e in entry.sub_entries.get("movedrecipes", [])],
        custom_foods=[map_custom_food(e) for e in entry.sub_entries.get("customfoods", [])],
    )


# -- File-level parsing --------------------------------------------------------


def _populate_parsed_file(
    result: ParsedFile,
    block_type: BlockType,
    entries: list[EntryBlock],
) -> None:
    """Dispatch on block type and populate the matching list on *result*."""
    if block_type is BlockType.MODIFIED_RECIPES:
        result.modified_recipes = [map_modified_recipe(e) for e in entries]
    elif block_type is BlockType.ADDED_RECIPES:
        result.added_recipes = [map_added_recipe(e) for e in entries]
    elif block_type is BlockType.ALIAS_RECIPES:
        result.alias_recipes = [map_alias_recipe(e) for e in entries]
    elif block_type is BlockType.CUSTOM_FOODS:
        result.custom_foods = [map_custom_food(e) for e in entries]
    elif block_type is BlockType.CUSTOM_CRAFTING_TABS:
        result.crafting_tabs = [map_crafting_tab(e) for e in entries]
    elif block_type is BlockType.CUSTOM_FABRICATORS:
        result.custom_fabricators = [map_custom_fabricator(e) for e in entries]
    elif block_type is BlockType.MOVED_RECIPES:
        result.moved_recipes = [map_moved_recipe(e) for e in entries]
    elif block_type is BlockType.CUSTOM_SIZES:
        result.custom_sizes = [map_custom_size(e) for e in entries]
    elif block_type is BlockType.CUSTOM_BIO_FUELS:
        result.custom_bio_fuels = [map_custom_bio_fuel(e) for e in entries]
    elif block_type is BlockType.CUSTOM_FRAGMENT_COUNTS:
        result.custom_fragment_counts = [map_custom_fragment_count(e) for e in entries]


def parse_text(text: str, source_path: Path) -> ParsedFile:
    """Parse raw EasyMarkup text into a ``ParsedFile``.

    Identical to ``parse_file`` but takes a string instead of reading from
    disk.  Used by the GUI code editor for live re-parsing.

    Raises ``ParseError`` for structural failures and ``MappingError``
    for entry-mapping failures (e.g. missing required fields).
    """
    cleaned = clean_value(text)
    if not cleaned:
        return ParsedFile(source_path=source_path)

    block = parse_blocks(cleaned)
    block_type = resolve_block_type(block.block_type)

    result = ParsedFile(source_path=source_path, block_type=block_type)
    _populate_parsed_file(result, block_type, block.entries)
    return result


def parse_file(path: Path) -> ParsedFile:
    """Parse a single CC3 ``.txt`` file into a fully typed ``ParsedFile``."""
    raw = path.read_text(encoding="utf-8-sig")
    return parse_text(raw, source_path=path)


# -- Directory-level parsing ---------------------------------------------------


def parse_directory(path: Path) -> list[ParsedFile]:
    """Walk a directory tree, parse every ``.txt`` file, and return results.

    Recursively discovers all ``.txt`` files under *path* using
    ``Path.rglob``. Each file is parsed via ``parse_file``; files that
    fail to parse (``ParseError``, ``MappingError``) or that contain no
    recognizable block (empty / comment-only) are skipped with a warning.

    Returns a list of successfully parsed ``ParsedFile`` objects, sorted
    by source path for deterministic ordering.

    Raises ``FileNotFoundError`` if *path* does not exist.
    Raises ``NotADirectoryError`` if *path* is not a directory.
    """
    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")

    results: list[ParsedFile] = []
    for txt_file in sorted(path.rglob("*.txt")):
        try:
            parsed = parse_file(txt_file)
        except (ParseError, MappingError) as exc:
            logger.warning("Skipping %s: %s", txt_file, exc)
            continue

        if parsed.block_type is None:
            logger.debug("Skipping %s: empty or comment-only", txt_file)
            continue

        results.append(parsed)

    return results


# -- Validation ----------------------------------------------------------------


def validate_parsed_file(parsed: ParsedFile) -> list[str]:
    """Optional post-parse validation. Returns warning strings (empty = clean)."""
    warnings: list[str] = []
    _validate_ingredient_ranges(parsed, warnings)
    return warnings


def _validate_ingredient_ranges(parsed: ParsedFile, warnings: list[str]) -> None:
    """Check that all ingredient Required values fall within CC3's valid range."""
    limits = get_config().limits
    req_min = limits.ingredient_required_min
    req_max = limits.ingredient_required_max
    for recipe in parsed.all_recipes:
        for ing in recipe.ingredients:
            if not (req_min <= ing.required <= req_max):
                warnings.append(
                    f"{parsed.source_path.name}: ingredient '{ing.item_id}' "
                    f"in recipe '{recipe.item_id}' has Required={ing.required} "
                    f"(valid range: {req_min}-{req_max})"
                )
    # CustomFabricator build-cost ingredients are NOT in all_recipes
    for fab in parsed.custom_fabricators:
        for ing in fab.ingredients:
            if not (req_min <= ing.required <= req_max):
                warnings.append(
                    f"{parsed.source_path.name}: ingredient '{ing.item_id}' "
                    f"in fabricator '{fab.item_id}' has Required={ing.required} "
                    f"(valid range: {req_min}-{req_max})"
                )


# -- ID extraction -------------------------------------------------------------


def _collect_recipe_ids(recipe: ModifiedRecipe, ids: set[str]) -> None:
    """Collect all TechType IDs from a recipe and its fields."""
    ids.add(recipe.item_id)
    for ing in recipe.ingredients:
        ids.add(ing.item_id)
    ids.update(recipe.linked_item_ids)
    ids.update(recipe.unlocks)
    ids.update(recipe.unlocked_by)
    if isinstance(recipe, AliasRecipe):
        if recipe.functional_id is not None:
            ids.add(recipe.functional_id)
        if recipe.sprite_item_id is not None:
            ids.add(recipe.sprite_item_id)


def _collect_tab_ids(tab: CraftingTab, ids: set[str]) -> None:
    """Collect TechType IDs from a crafting tab."""
    ids.add(tab.tab_id)
    if tab.sprite_item_id is not None:
        ids.add(tab.sprite_item_id)


def extract_ids(parsed_files: list[ParsedFile]) -> set[str]:
    """Collect every TechType ID referenced in *parsed_files*.

    Walks all block types (recipes, fabricators, tabs, sizes, bio fuels,
    fragment counts) and returns the union of all IDs found.  The caller
    is responsible for filtering out vanilla or mod-compat IDs if desired.
    """
    ids: set[str] = set()
    for pf in parsed_files:
        for recipe in pf.all_recipes:
            _collect_recipe_ids(recipe, ids)
        for tab in pf.crafting_tabs:
            _collect_tab_ids(tab, ids)
        for fab in pf.custom_fabricators:
            ids.add(fab.item_id)
            for ing in fab.ingredients:
                ids.add(ing.item_id)
            ids.update(fab.unlocked_by)
            for tab in fab.tabs:
                _collect_tab_ids(tab, ids)
            # added_recipes, alias_recipes, custom_foods already covered
            # by pf.all_recipes above; only moved_recipes is exclusive
            for r in fab.moved_recipes:
                ids.add(r.item_id)
        for mr in pf.moved_recipes:
            ids.add(mr.item_id)
        for cs in pf.custom_sizes:
            ids.add(cs.item_id)
        for bf in pf.custom_bio_fuels:
            ids.add(bf.item_id)
        for fc in pf.custom_fragment_counts:
            ids.add(fc.item_id)
    return ids
