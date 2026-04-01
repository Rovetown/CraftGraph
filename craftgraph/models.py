"""Data model for CraftGraph recipe entries.

Maps the 10 CustomCraft3 EasyMarkup block types into Python dataclasses.
The hierarchy mirrors CC3's own inheritance:

    ModifiedRecipe -> AddedRecipe -> AliasRecipe -> CustomFood
                                                 -> CustomFabricator (composition)

Each parsed .txt file produces a single ParsedFile containing entries of one
block type. A mod folder is represented as a list[ParsedFile].
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class BlockType(Enum):
    """Top-level block types recognized in CC3 EasyMarkup files."""

    MODIFIED_RECIPES = "ModifiedRecipes"
    ADDED_RECIPES = "AddedRecipes"
    ALIAS_RECIPES = "AliasRecipes"
    CUSTOM_CRAFTING_TABS = "CustomCraftingTabs"
    CUSTOM_FABRICATORS = "CustomFabricators"
    MOVED_RECIPES = "MovedRecipes"
    CUSTOM_SIZES = "CustomSizes"
    CUSTOM_BIO_FUELS = "CustomBioFuels"
    CUSTOM_FRAGMENT_COUNTS = "CustomFragmentCounts"
    CUSTOM_FOODS = "CustomFoods"


# ---------------------------------------------------------------------------
# CraftTree.Type (vanilla crafting station identifiers)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CraftTreeEntry:
    """A vanilla crafting station from Subnautica's ``CraftTree.Type`` enum.

    Attributes:
        value: The ``CraftTree.Type`` enum member name (e.g. ``"MapRoom"``).
        label: Human-readable in-game name (e.g. ``"Scanner Room"``).
        tree_root: The actual crafting tree root path name used as a Path
            prefix in CC3 files.  Usually identical to *value*, except for
            ``MapRoom`` whose tree root is ``MapRoomFunctionality``.
        below_zero_only: ``True`` if this station exists only in Below Zero
            and is unavailable / cut content in Subnautica 1.
    """

    value: str
    label: str
    tree_root: str
    below_zero_only: bool = False


CRAFT_TREE_TYPES: tuple[CraftTreeEntry, ...] = (
    CraftTreeEntry("Fabricator", "Standard Fabricator", "Fabricator"),
    CraftTreeEntry("Workbench", "Modification Station", "Workbench"),
    CraftTreeEntry("Constructor", "Mobile Vehicle Bay", "Constructor"),
    CraftTreeEntry("CyclopsFabricator", "Cyclops Fabricator", "CyclopsFabricator"),
    CraftTreeEntry("SeamothUpgrades", "Vehicle Upgrade Console", "SeamothUpgrades"),
    CraftTreeEntry("MapRoom", "Scanner Room", "MapRoomFunctionality"),
    CraftTreeEntry("Rocket", "Neptune Launch Platform", "Rocket"),
    CraftTreeEntry(
        "Centrifuge", "Centrifuge", "Centrifuge", below_zero_only=True,
    ),
)

SN1_CRAFT_TREE_PATH_ROOTS: frozenset[str] = frozenset(
    ct.tree_root for ct in CRAFT_TREE_TYPES if not ct.below_zero_only
)


# ---------------------------------------------------------------------------
# CC3 enum value lists (authoritative, from C# source)
# ---------------------------------------------------------------------------

FABRICATOR_MODELS: tuple[str, ...] = ("Fabricator", "Workbench", "MoonPool")

TECH_GROUPS: tuple[str, ...] = (
    "Uncategorized",
    "Resources",
    "Survival",
    "Personal",
    "Machines",
    "InteriorModules",
    "InteriorPieces",
    "ExteriorModules",
    "BasePieces",
    "Cyclops",
    "Constructor",
    "Miscellaneous",
    "VehicleUpgrades",
    "MapRoomUpgrades",
)

TECH_CATEGORIES: tuple[str, ...] = (
    "Misc",
    "BasicMaterials",
    "AdvancedMaterials",
    "Electronics",
    "Water",
    "CookedFood",
    "CuredFood",
    "FoodAndDrinks",
    "Equipment",
    "Tools",
    "Machines",
    "InteriorModule",
    "InteriorPiece",
    "ExteriorModule",
    "BasePiece",
    "BaseRoom",
    "BaseWall",
    "CyclopsUpgrades",
    "Constructor",
    "VehicleUpgrades",
    "MapRoomUpgrades",
    "Rocket",
    "Workbench",
)

FOOD_MODELS: tuple[str, ...] = (
    "None",
    "BigFilteredWater",
    "DisinfectedWater",
    "FilteredWater",
    "WaterFiltrationSuitWater",
    "BulboTreePiece",
    "PurpleVegetable",
    "CreepvinePiece",
    "JellyPlant",
    "KooshChunk",
    "HangingFruit",
    "Melon",
    "NutrientBlock",
    "CookedPeeper",
    "CookedHoleFish",
    "CookedGarryFish",
    "CookedReginald",
    "CookedBladderfish",
    "CookedHoverfish",
    "CookedSpadefish",
    "CookedBoomerang",
    "CookedEyeye",
    "CookedOculus",
    "CookedHoopfish",
    "CookedSpinefish",
    "CookedLavaEyeye",
    "CookedLavaBoomerang",
    "CuredPeeper",
    "CuredHoleFish",
    "CuredGarryFish",
    "CuredReginald",
    "CuredBladderfish",
    "CuredHoverfish",
    "CuredSpadefish",
    "CuredBoomerang",
    "CuredEyeye",
    "CuredOculus",
    "CuredHoopfish",
    "CuredSpinefish",
    "CuredLavaEyeye",
    "CuredLavaBoomerang",
)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ingredient:
    """A single ingredient requirement within a recipe."""

    item_id: str
    required: int


# ---------------------------------------------------------------------------
# Recipe hierarchy
# ---------------------------------------------------------------------------


@dataclass
class ModifiedRecipe:
    """An entry that modifies an existing in-game recipe.

    This is the base type. All recipe-like block types share these fields.
    """

    item_id: str
    amount_crafted: int = 1
    ingredients: list[Ingredient] = field(default_factory=list)
    linked_item_ids: list[str] = field(default_factory=list)
    unlocks: list[str] = field(default_factory=list)
    force_unlock_at_start: bool | None = None
    unlocked_by: list[str] = field(default_factory=list)


@dataclass
class AddedRecipe(ModifiedRecipe):
    """A brand-new recipe added to an existing fabricator.

    Extends ModifiedRecipe with placement information.
    """

    path: str = ""
    pda_group: str | None = None
    pda_category: str | None = None


@dataclass
class AliasRecipe(AddedRecipe):
    """An alias recipe for alternative crafting paths or custom items.

    Extends AddedRecipe with display and identity fields.
    AliasRecipes typically use LinkedItemIDs rather than AmountCrafted.
    """

    display_name: str = ""
    tooltip: str = ""
    functional_id: str | None = None
    sprite_item_id: str | None = None


@dataclass
class CustomFood(AliasRecipe):
    """A custom consumable item with nutrition stats.

    Extends AliasRecipe with food/water/health values.
    """

    food_value: int = 0
    water_value: int = 0
    oxygen_value: int = 0
    health_value: int = 0
    decay_rate_mod: float = 0.0
    food_type: str | None = None
    use_drink_sound: bool | None = None


# ---------------------------------------------------------------------------
# Non-recipe entry types
# ---------------------------------------------------------------------------


@dataclass
class CraftingTab:
    """A custom tab in a fabricator's crafting tree."""

    tab_id: str
    display_name: str = ""
    sprite_item_id: str | None = None
    parent_tab_path: str = ""


@dataclass
class MovedRecipe:
    """A directive to relocate, copy, or hide an existing recipe node."""

    item_id: str
    old_path: str | None = None
    new_path: str | None = None
    copied: bool = False
    hidden: bool = False


@dataclass
class CustomFabricator:
    """A fully custom fabricator with its own crafting tree.

    Contains nested lists of tabs and recipes that live inside this fabricator.
    """

    item_id: str
    display_name: str = ""
    tooltip: str = ""
    model: str = "Fabricator"
    color_tint: list[float] = field(default_factory=list)
    allowed_in_base: bool = True
    allowed_in_cyclops: bool = True
    ingredients: list[Ingredient] = field(default_factory=list)
    pda_group: str | None = None
    pda_category: str | None = None
    force_unlock_at_start: bool | None = None
    unlocked_by: list[str] = field(default_factory=list)
    # Nested crafting tree contents
    tabs: list[CraftingTab] = field(default_factory=list)
    added_recipes: list[AddedRecipe] = field(default_factory=list)
    alias_recipes: list[AliasRecipe] = field(default_factory=list)
    moved_recipes: list[MovedRecipe] = field(default_factory=list)
    custom_foods: list[CustomFood] = field(default_factory=list)


@dataclass
class CustomSize:
    """Custom inventory slot dimensions for an item."""

    item_id: str
    width: int = 1
    height: int = 1


@dataclass
class CustomBioFuel:
    """Custom BioReactor energy value for an item."""

    item_id: str
    energy: float = 0.0


@dataclass
class CustomFragmentCount:
    """Custom number of fragments needed to unlock a blueprint."""

    item_id: str
    fragments_to_scan: int = 1


# ---------------------------------------------------------------------------
# File-level container
# ---------------------------------------------------------------------------


# Type alias for non-recipe entry types (used in commands and GUI layers)
NonRecipeEntry = (
    CraftingTab | CustomFabricator | MovedRecipe | CustomSize | CustomBioFuel | CustomFragmentCount
)


@dataclass
class ParsedFile:
    """All entries parsed from a single CC3 .txt file.

    A mod folder is a collection of .txt files, each parsed independently.
    The block_type indicates which top-level keyword was found, and only the
    corresponding list will be populated.
    """

    source_path: Path
    block_type: BlockType | None = None

    modified_recipes: list[ModifiedRecipe] = field(default_factory=list)
    added_recipes: list[AddedRecipe] = field(default_factory=list)
    alias_recipes: list[AliasRecipe] = field(default_factory=list)
    custom_foods: list[CustomFood] = field(default_factory=list)
    crafting_tabs: list[CraftingTab] = field(default_factory=list)
    custom_fabricators: list[CustomFabricator] = field(default_factory=list)
    moved_recipes: list[MovedRecipe] = field(default_factory=list)
    custom_sizes: list[CustomSize] = field(default_factory=list)
    custom_bio_fuels: list[CustomBioFuel] = field(default_factory=list)
    custom_fragment_counts: list[CustomFragmentCount] = field(default_factory=list)

    @property
    def all_recipes(self) -> list[ModifiedRecipe]:
        """Every recipe-like entry in this file, regardless of subtype.

        Useful for the graph builder, which needs to iterate all recipes
        to extract dependency edges. Also includes recipes nested inside
        custom fabricators.
        """
        recipes: list[ModifiedRecipe] = []
        recipes.extend(self.modified_recipes)
        recipes.extend(self.added_recipes)
        recipes.extend(self.alias_recipes)
        recipes.extend(self.custom_foods)
        for fab in self.custom_fabricators:
            recipes.extend(fab.added_recipes)
            recipes.extend(fab.alias_recipes)
            recipes.extend(fab.custom_foods)
        return recipes
