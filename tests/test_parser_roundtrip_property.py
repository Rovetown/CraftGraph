"""Property-based roundtrip tests for parser <-> serializer.

For each block type, we generate a realistic ``ParsedFile``, serialize it,
parse the resulting text, and assert the result equals the original. This
catches asymmetries that example-based tests miss (escape edge cases,
field-order dependencies, default-omission round-tripping).

Strategies stay inside the realistic input domain: TechType-like IDs
(alphanumeric + underscore), bounded list sizes, printable ASCII for
display fields. Adversarial-input fuzzing of the parser is out of scope --
``test_serializer.TestEscapeValue`` and ``test_parser`` cover that surface
directly.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from craftgraph.models import (
    AddedRecipe,
    AliasRecipe,
    BlockType,
    CraftingTab,
    CustomBioFuel,
    CustomFragmentCount,
    CustomSize,
    Ingredient,
    ModifiedRecipe,
    MovedRecipe,
    ParsedFile,
)
from craftgraph.parser import parse_text
from craftgraph.serializer import serialize_file

# ---------------------------------------------------------------------------
# Atomic strategies
# ---------------------------------------------------------------------------

# TechType-like identifiers: must start with a letter, then alnum / underscore.
ids = st.from_regex(r"\A[A-Za-z][A-Za-z0-9_]{0,29}\Z")

# Display strings: printable ASCII minus the EasyMarkup specials and quote.
_DISPLAY_ALPHABET = st.characters(
    min_codepoint=0x20,
    max_codepoint=0x7E,
    blacklist_characters=':;(),#\\"',
)
display_strings = st.text(alphabet=_DISPLAY_ALPHABET, min_size=0, max_size=40)

# Path fields are slash-separated TechType-like segments.
paths = st.lists(ids, min_size=1, max_size=4).map("/".join)

# Optional bool: YES/NO emitted only when not None.
opt_bool = st.one_of(st.none(), st.booleans())


# ---------------------------------------------------------------------------
# Composite strategies (one per recipe / entry type)
# ---------------------------------------------------------------------------


@st.composite
def ingredients(draw: st.DrawFn) -> Ingredient:
    return Ingredient(
        item_id=draw(ids),
        required=draw(st.integers(min_value=1, max_value=99)),
    )


@st.composite
def modified_recipes(draw: st.DrawFn) -> ModifiedRecipe:
    return ModifiedRecipe(
        item_id=draw(ids),
        amount_crafted=draw(st.integers(min_value=1, max_value=99)),
        ingredients=draw(st.lists(ingredients(), max_size=6)),
        linked_item_ids=draw(st.lists(ids, max_size=4)),
        unlocks=draw(st.lists(ids, max_size=4)),
        force_unlock_at_start=draw(opt_bool),
        unlocked_by=draw(st.lists(ids, max_size=4)),
    )


@st.composite
def added_recipes(draw: st.DrawFn) -> AddedRecipe:
    return AddedRecipe(
        item_id=draw(ids),
        amount_crafted=draw(st.integers(min_value=1, max_value=99)),
        ingredients=draw(st.lists(ingredients(), max_size=6)),
        linked_item_ids=draw(st.lists(ids, max_size=4)),
        unlocks=draw(st.lists(ids, max_size=4)),
        force_unlock_at_start=draw(opt_bool),
        unlocked_by=draw(st.lists(ids, max_size=4)),
        path=draw(st.one_of(st.just(""), paths)),
        pda_group=draw(st.one_of(st.none(), ids)),
        pda_category=draw(st.one_of(st.none(), ids)),
    )


@st.composite
def alias_recipes(draw: st.DrawFn) -> AliasRecipe:
    return AliasRecipe(
        item_id=draw(ids),
        amount_crafted=draw(st.integers(min_value=1, max_value=99)),
        ingredients=draw(st.lists(ingredients(), max_size=6)),
        linked_item_ids=draw(st.lists(ids, max_size=4)),
        unlocks=draw(st.lists(ids, max_size=4)),
        force_unlock_at_start=draw(opt_bool),
        unlocked_by=draw(st.lists(ids, max_size=4)),
        path=draw(st.one_of(st.just(""), paths)),
        pda_group=draw(st.one_of(st.none(), ids)),
        pda_category=draw(st.one_of(st.none(), ids)),
        display_name=draw(display_strings),
        tooltip=draw(display_strings),
        functional_id=draw(st.one_of(st.none(), ids)),
        sprite_item_id=draw(st.one_of(st.none(), ids)),
    )


@st.composite
def crafting_tabs(draw: st.DrawFn) -> CraftingTab:
    return CraftingTab(
        tab_id=draw(ids),
        display_name=draw(display_strings),
        sprite_item_id=draw(st.one_of(st.none(), ids)),
        parent_tab_path=draw(st.one_of(st.just(""), paths)),
    )


@st.composite
def moved_recipes(draw: st.DrawFn) -> MovedRecipe:
    return MovedRecipe(
        item_id=draw(ids),
        old_path=draw(st.one_of(st.none(), paths)),
        new_path=draw(st.one_of(st.none(), paths)),
        copied=draw(st.booleans()),
        hidden=draw(st.booleans()),
    )


@st.composite
def custom_sizes(draw: st.DrawFn) -> CustomSize:
    return CustomSize(
        item_id=draw(ids),
        width=draw(st.integers(min_value=1, max_value=8)),
        height=draw(st.integers(min_value=1, max_value=8)),
    )


# Floats serialized via _float_str use ``f"{value:g}"`` which gives 6 sig figs.
# Restrict to one decimal place so roundtrip is exact regardless of float repr.
_safe_energy = st.integers(min_value=0, max_value=1000).map(lambda n: n / 10.0)


@st.composite
def custom_bio_fuels(draw: st.DrawFn) -> CustomBioFuel:
    return CustomBioFuel(item_id=draw(ids), energy=draw(_safe_energy))


@st.composite
def custom_fragment_counts(draw: st.DrawFn) -> CustomFragmentCount:
    return CustomFragmentCount(
        item_id=draw(ids),
        fragments_to_scan=draw(st.integers(min_value=1, max_value=20)),
    )


# ---------------------------------------------------------------------------
# Property: parse(serialize(file)) == file
# ---------------------------------------------------------------------------


SETTINGS = settings(
    max_examples=75,
    deadline=None,
    # Strategies build small dataclasses; the cost is in parse+serialize.
    suppress_health_check=[HealthCheck.too_slow],
)

_FAKE_PATH = Path("hypothesis_roundtrip.txt")


def _roundtrip(parsed: ParsedFile) -> ParsedFile:
    return parse_text(serialize_file(parsed), source_path=_FAKE_PATH)


@SETTINGS
@given(entries=st.lists(modified_recipes(), min_size=1, max_size=5))
def test_modified_recipes_roundtrip(entries: list[ModifiedRecipe]) -> None:
    pf = ParsedFile(_FAKE_PATH, block_type=BlockType.MODIFIED_RECIPES, modified_recipes=entries)
    result = _roundtrip(pf)
    assert result.block_type is BlockType.MODIFIED_RECIPES
    assert result.modified_recipes == entries


@SETTINGS
@given(entries=st.lists(added_recipes(), min_size=1, max_size=5))
def test_added_recipes_roundtrip(entries: list[AddedRecipe]) -> None:
    pf = ParsedFile(_FAKE_PATH, block_type=BlockType.ADDED_RECIPES, added_recipes=entries)
    result = _roundtrip(pf)
    assert result.block_type is BlockType.ADDED_RECIPES
    assert result.added_recipes == entries


@SETTINGS
@given(entries=st.lists(alias_recipes(), min_size=1, max_size=5))
def test_alias_recipes_roundtrip(entries: list[AliasRecipe]) -> None:
    pf = ParsedFile(_FAKE_PATH, block_type=BlockType.ALIAS_RECIPES, alias_recipes=entries)
    result = _roundtrip(pf)
    assert result.block_type is BlockType.ALIAS_RECIPES
    assert result.alias_recipes == entries


@SETTINGS
@given(entries=st.lists(crafting_tabs(), min_size=1, max_size=5))
def test_crafting_tabs_roundtrip(entries: list[CraftingTab]) -> None:
    pf = ParsedFile(_FAKE_PATH, block_type=BlockType.CUSTOM_CRAFTING_TABS, crafting_tabs=entries)
    result = _roundtrip(pf)
    assert result.block_type is BlockType.CUSTOM_CRAFTING_TABS
    assert result.crafting_tabs == entries


@SETTINGS
@given(entries=st.lists(moved_recipes(), min_size=1, max_size=5))
def test_moved_recipes_roundtrip(entries: list[MovedRecipe]) -> None:
    pf = ParsedFile(_FAKE_PATH, block_type=BlockType.MOVED_RECIPES, moved_recipes=entries)
    result = _roundtrip(pf)
    assert result.block_type is BlockType.MOVED_RECIPES
    assert result.moved_recipes == entries


@SETTINGS
@given(entries=st.lists(custom_sizes(), min_size=1, max_size=5))
def test_custom_sizes_roundtrip(entries: list[CustomSize]) -> None:
    pf = ParsedFile(_FAKE_PATH, block_type=BlockType.CUSTOM_SIZES, custom_sizes=entries)
    result = _roundtrip(pf)
    assert result.block_type is BlockType.CUSTOM_SIZES
    assert result.custom_sizes == entries


@SETTINGS
@given(entries=st.lists(custom_bio_fuels(), min_size=1, max_size=5))
def test_custom_bio_fuels_roundtrip(entries: list[CustomBioFuel]) -> None:
    pf = ParsedFile(_FAKE_PATH, block_type=BlockType.CUSTOM_BIO_FUELS, custom_bio_fuels=entries)
    result = _roundtrip(pf)
    assert result.block_type is BlockType.CUSTOM_BIO_FUELS
    assert result.custom_bio_fuels == entries


@SETTINGS
@given(entries=st.lists(custom_fragment_counts(), min_size=1, max_size=5))
def test_custom_fragment_counts_roundtrip(entries: list[CustomFragmentCount]) -> None:
    pf = ParsedFile(
        _FAKE_PATH,
        block_type=BlockType.CUSTOM_FRAGMENT_COUNTS,
        custom_fragment_counts=entries,
    )
    result = _roundtrip(pf)
    assert result.block_type is BlockType.CUSTOM_FRAGMENT_COUNTS
    assert result.custom_fragment_counts == entries
