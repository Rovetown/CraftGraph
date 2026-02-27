"""Command pattern for undo/redo in the interactive node editor.

Every model mutation is wrapped in an EditCommand with execute() and undo()
methods. EditHistory manages the undo/redo stacks and dirty tracking.

This module has NO DPG dependency -- it operates purely on the data model.
All commands are fully unit testable without a GUI context.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

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
    NonRecipeEntry,
    ParsedFile,
)

# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class EditCommand(ABC):
    """A reversible edit operation on the data model."""

    @abstractmethod
    def execute(self) -> None:
        """Apply the edit to the model."""

    @abstractmethod
    def undo(self) -> None:
        """Reverse the edit, restoring the previous state."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of this edit (for UI display)."""


# ---------------------------------------------------------------------------
# Edit history (undo/redo stacks + dirty tracking)
# ---------------------------------------------------------------------------


class EditHistory:
    """Manages undo/redo stacks and tracks whether the model is dirty.

    The ``on_change`` callback fires after every execute, undo, or redo so
    the GUI layer can refresh visuals and update the status bar.
    """

    def __init__(self, on_change: Callable[[], None] | None = None) -> None:
        self._undo_stack: list[EditCommand] = []
        self._redo_stack: list[EditCommand] = []
        self._save_index: int = 0
        self.on_change = on_change

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    @property
    def is_dirty(self) -> bool:
        """True if the model has unsaved changes."""
        return len(self._undo_stack) != self._save_index

    @property
    def undo_description(self) -> str:
        """Description of the next command that would be undone."""
        if not self._undo_stack:
            return ""
        return self._undo_stack[-1].description

    @property
    def redo_description(self) -> str:
        """Description of the next command that would be redone."""
        if not self._redo_stack:
            return ""
        return self._redo_stack[-1].description

    def execute(self, command: EditCommand) -> None:
        """Execute a command, pushing it onto the undo stack.

        Clears the redo stack (new edit invalidates the redo future).
        """
        command.execute()
        self._undo_stack.append(command)
        self._redo_stack.clear()
        if self.on_change is not None:
            self.on_change()

    def execute_silent(self, command: EditCommand) -> None:
        """Execute a command without triggering the on_change callback.

        Used for incremental visual updates (e.g. link swaps) where the
        caller handles the visual refresh manually.  Undo/redo of the
        command still fires the callback as normal.
        """
        command.execute()
        self._undo_stack.append(command)
        self._redo_stack.clear()

    def undo(self) -> None:
        """Undo the most recent command."""
        if not self._undo_stack:
            return
        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)
        if self.on_change is not None:
            self.on_change()

    def redo(self) -> None:
        """Redo the most recently undone command."""
        if not self._redo_stack:
            return
        command = self._redo_stack.pop()
        command.execute()
        self._undo_stack.append(command)
        if self.on_change is not None:
            self.on_change()

    def mark_saved(self) -> None:
        """Record the current position as the saved state."""
        self._save_index = len(self._undo_stack)

    def clear(self) -> None:
        """Reset all history (e.g. after reloading from disk)."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._save_index = 0


# ---------------------------------------------------------------------------
# Concrete commands
# ---------------------------------------------------------------------------


@dataclass
class AddIngredientCommand(EditCommand):
    """Append an ingredient to a recipe's ingredient list."""

    recipe: ModifiedRecipe
    ingredient: Ingredient

    def execute(self) -> None:
        self.recipe.ingredients.append(self.ingredient)

    def undo(self) -> None:
        self.recipe.ingredients.pop()

    @property
    def description(self) -> str:
        return f"Add {self.ingredient.item_id} to {self.recipe.item_id}"


@dataclass
class RemoveIngredientCommand(EditCommand):
    """Remove an ingredient from a recipe by index.

    Captures the removed ingredient and its index for undo.
    """

    recipe: ModifiedRecipe
    index: int
    _captured: Ingredient | None = None

    def execute(self) -> None:
        self._captured = self.recipe.ingredients[self.index]
        self.recipe.ingredients.pop(self.index)

    def undo(self) -> None:
        if self._captured is not None:
            self.recipe.ingredients.insert(self.index, self._captured)

    @property
    def description(self) -> str:
        name = self._captured.item_id if self._captured else f"index {self.index}"
        return f"Remove {name} from {self.recipe.item_id}"


@dataclass
class ChangeIngredientCommand(EditCommand):
    """Replace an ingredient at a given index with a new one.

    Since Ingredient is frozen, this swaps the entire object.
    """

    recipe: ModifiedRecipe
    index: int
    new_ingredient: Ingredient
    _old_ingredient: Ingredient | None = None

    def execute(self) -> None:
        self._old_ingredient = self.recipe.ingredients[self.index]
        self.recipe.ingredients[self.index] = self.new_ingredient

    def undo(self) -> None:
        if self._old_ingredient is not None:
            self.recipe.ingredients[self.index] = self._old_ingredient

    @property
    def description(self) -> str:
        return f"Change ingredient {self.index} of {self.recipe.item_id}"


@dataclass
class ChangeRecipeFieldCommand(EditCommand):
    """Change a scalar field on a recipe via setattr/getattr."""

    recipe: ModifiedRecipe
    field_name: str
    new_value: object
    _old_value: object = None

    def execute(self) -> None:
        self._old_value = getattr(self.recipe, self.field_name)
        setattr(self.recipe, self.field_name, self.new_value)

    def undo(self) -> None:
        setattr(self.recipe, self.field_name, self._old_value)

    @property
    def description(self) -> str:
        return f"Change {self.field_name} of {self.recipe.item_id}"


@dataclass
class ChangeNonRecipeFieldCommand(EditCommand):
    """Change a scalar field on a non-recipe entry via setattr/getattr."""

    entry: NonRecipeEntry
    field_name: str
    new_value: object
    _old_value: object = None

    def execute(self) -> None:
        self._old_value = getattr(self.entry, self.field_name)
        setattr(self.entry, self.field_name, self.new_value)

    def undo(self) -> None:
        setattr(self.entry, self.field_name, self._old_value)

    @property
    def description(self) -> str:
        entry_id = _entry_id(self.entry)
        return f"Change {self.field_name} of {entry_id}"


# ---------------------------------------------------------------------------
# Recipe-level block type mapping
# ---------------------------------------------------------------------------

# Maps recipe class to (ParsedFile list attribute, BlockType).
_RECIPE_TYPE_TO_LIST: dict[type, tuple[str, BlockType]] = {
    CustomFood: ("custom_foods", BlockType.CUSTOM_FOODS),
    AliasRecipe: ("alias_recipes", BlockType.ALIAS_RECIPES),
    AddedRecipe: ("added_recipes", BlockType.ADDED_RECIPES),
    ModifiedRecipe: ("modified_recipes", BlockType.MODIFIED_RECIPES),
}


def _list_attr_for_recipe(recipe: ModifiedRecipe) -> str:
    """Return the ParsedFile list attribute name for a recipe's concrete type.

    Checks from most-derived to least-derived (CustomFood before AliasRecipe
    before AddedRecipe before ModifiedRecipe) because isinstance matches
    parent classes too.
    """
    for cls, (attr, _block_type) in _RECIPE_TYPE_TO_LIST.items():
        if type(recipe) is cls:
            return attr
    return "modified_recipes"


# ---------------------------------------------------------------------------
# Add / Remove recipe commands
# ---------------------------------------------------------------------------


@dataclass
class AddRecipeCommand(EditCommand):
    """Add a new recipe to the appropriate list in a ParsedFile."""

    parsed_file: ParsedFile
    recipe: ModifiedRecipe
    _list_attr: str = ""

    def execute(self) -> None:
        self._list_attr = _list_attr_for_recipe(self.recipe)
        recipe_list: list[ModifiedRecipe] = getattr(self.parsed_file, self._list_attr)
        recipe_list.append(self.recipe)

    def undo(self) -> None:
        recipe_list: list[ModifiedRecipe] = getattr(self.parsed_file, self._list_attr)
        recipe_list.pop()

    @property
    def description(self) -> str:
        return f"Add recipe {self.recipe.item_id}"


@dataclass
class RemoveRecipeCommand(EditCommand):
    """Remove a recipe from its ParsedFile list.

    Captures the recipe and its index for undo.
    """

    parsed_file: ParsedFile
    recipe: ModifiedRecipe
    _list_attr: str = ""
    _index: int = -1

    def execute(self) -> None:
        self._list_attr = _list_attr_for_recipe(self.recipe)
        recipe_list: list[ModifiedRecipe] = getattr(self.parsed_file, self._list_attr)
        self._index = recipe_list.index(self.recipe)
        recipe_list.pop(self._index)

    def undo(self) -> None:
        recipe_list: list[ModifiedRecipe] = getattr(self.parsed_file, self._list_attr)
        recipe_list.insert(self._index, self.recipe)

    @property
    def description(self) -> str:
        return f"Remove recipe {self.recipe.item_id}"


# ---------------------------------------------------------------------------
# Non-recipe block type mapping
# ---------------------------------------------------------------------------

_NON_RECIPE_TYPE_TO_LIST: dict[type, tuple[str, BlockType]] = {
    CustomFabricator: ("custom_fabricators", BlockType.CUSTOM_FABRICATORS),
    CraftingTab: ("crafting_tabs", BlockType.CUSTOM_CRAFTING_TABS),
    MovedRecipe: ("moved_recipes", BlockType.MOVED_RECIPES),
    CustomSize: ("custom_sizes", BlockType.CUSTOM_SIZES),
    CustomBioFuel: ("custom_bio_fuels", BlockType.CUSTOM_BIO_FUELS),
    CustomFragmentCount: ("custom_fragment_counts", BlockType.CUSTOM_FRAGMENT_COUNTS),
}


def _list_attr_for_non_recipe(entry: NonRecipeEntry) -> str:
    """Return the ParsedFile list attribute name for a non-recipe entry's type."""
    for cls, (attr, _block_type) in _NON_RECIPE_TYPE_TO_LIST.items():
        if type(entry) is cls:
            return attr
    msg = f"Unknown non-recipe type: {type(entry).__name__}"
    raise TypeError(msg)


def _entry_id(entry: NonRecipeEntry) -> str:
    """Return the primary identifier for any non-recipe entry."""
    if isinstance(entry, CraftingTab):
        return entry.tab_id
    return entry.item_id


# ---------------------------------------------------------------------------
# Add / Remove non-recipe commands
# ---------------------------------------------------------------------------


@dataclass
class AddNonRecipeCommand(EditCommand):
    """Add a non-recipe entry to the appropriate list in a ParsedFile."""

    parsed_file: ParsedFile
    entry: NonRecipeEntry
    _list_attr: str = ""

    def execute(self) -> None:
        self._list_attr = _list_attr_for_non_recipe(self.entry)
        entry_list: list[NonRecipeEntry] = getattr(self.parsed_file, self._list_attr)
        entry_list.append(self.entry)

    def undo(self) -> None:
        entry_list: list[NonRecipeEntry] = getattr(self.parsed_file, self._list_attr)
        entry_list.pop()

    @property
    def description(self) -> str:
        return f"Add {type(self.entry).__name__} {_entry_id(self.entry)}"


@dataclass
class RemoveNonRecipeCommand(EditCommand):
    """Remove a non-recipe entry from its ParsedFile list."""

    parsed_file: ParsedFile
    entry: NonRecipeEntry
    _list_attr: str = ""
    _index: int = -1

    def execute(self) -> None:
        self._list_attr = _list_attr_for_non_recipe(self.entry)
        entry_list: list[NonRecipeEntry] = getattr(self.parsed_file, self._list_attr)
        self._index = entry_list.index(self.entry)
        entry_list.pop(self._index)

    def undo(self) -> None:
        entry_list: list[NonRecipeEntry] = getattr(self.parsed_file, self._list_attr)
        entry_list.insert(self._index, self.entry)

    @property
    def description(self) -> str:
        return f"Remove {type(self.entry).__name__} {_entry_id(self.entry)}"


# ---------------------------------------------------------------------------
# Hierarchy nesting commands (fabricator -> tab -> recipe)
# ---------------------------------------------------------------------------


@dataclass
class NestTabInFabricatorCommand(EditCommand):
    """Move a crafting tab from top-level into a fabricator's nested tabs list.

    Sets ``tab.parent_tab_path`` to the fabricator's item_id.
    If the tab is in the top-level ``parsed_file.crafting_tabs`` list, it is
    removed from there first.
    """

    parsed_file: ParsedFile
    fabricator: CustomFabricator
    tab: CraftingTab
    _was_in_top_level: bool = False
    _top_level_index: int = -1
    _old_parent_tab_path: str = ""

    def execute(self) -> None:
        self._old_parent_tab_path = self.tab.parent_tab_path
        # Remove from top-level list if present
        if self.tab in self.parsed_file.crafting_tabs:
            self._top_level_index = self.parsed_file.crafting_tabs.index(self.tab)
            self.parsed_file.crafting_tabs.pop(self._top_level_index)
            self._was_in_top_level = True
        # Add to fabricator's nested tabs
        self.fabricator.tabs.append(self.tab)
        self.tab.parent_tab_path = self.fabricator.item_id

    def undo(self) -> None:
        self.fabricator.tabs.remove(self.tab)
        if self._was_in_top_level:
            self.parsed_file.crafting_tabs.insert(self._top_level_index, self.tab)
        self.tab.parent_tab_path = self._old_parent_tab_path

    @property
    def description(self) -> str:
        return f"Nest tab {self.tab.tab_id} in {self.fabricator.item_id}"


# Maps recipe concrete type to (ParsedFile attr, CustomFabricator attr).
_RECIPE_NESTING_MAP: dict[type, tuple[str, str]] = {
    CustomFood: ("custom_foods", "custom_foods"),
    AliasRecipe: ("alias_recipes", "alias_recipes"),
    AddedRecipe: ("added_recipes", "added_recipes"),
}


@dataclass
class NestRecipeInFabricatorCommand(EditCommand):
    """Move a recipe from top-level into a fabricator's nested recipe list.

    Sets ``recipe.path`` to the given path string (fab root or tab full path).
    Dispatches to the correct list pair based on the recipe's concrete type.
    """

    parsed_file: ParsedFile
    fabricator: CustomFabricator
    recipe: ModifiedRecipe
    path: str
    _pf_attr: str = ""
    _fab_attr: str = ""
    _was_in_top_level: bool = False
    _top_level_index: int = -1
    _old_path: str = ""

    def execute(self) -> None:
        self._old_path = getattr(self.recipe, "path", "")
        # Resolve which list pair to use
        for cls, (pf_a, fab_a) in _RECIPE_NESTING_MAP.items():
            if type(self.recipe) is cls:
                self._pf_attr = pf_a
                self._fab_attr = fab_a
                break
        else:
            # ModifiedRecipe cannot be nested in a fabricator in CC3.
            # Silently skip (validation layer will warn later in Step 11j).
            return

        # Remove from top-level list if present
        pf_list: list[ModifiedRecipe] = getattr(self.parsed_file, self._pf_attr)
        if self.recipe in pf_list:
            self._top_level_index = pf_list.index(self.recipe)
            pf_list.pop(self._top_level_index)
            self._was_in_top_level = True

        # Add to fabricator's nested list
        fab_list: list[ModifiedRecipe] = getattr(self.fabricator, self._fab_attr)
        fab_list.append(self.recipe)
        self.recipe.path = self.path

    def undo(self) -> None:
        if not self._fab_attr:
            return
        fab_list: list[ModifiedRecipe] = getattr(self.fabricator, self._fab_attr)
        fab_list.remove(self.recipe)
        if self._was_in_top_level:
            pf_list: list[ModifiedRecipe] = getattr(self.parsed_file, self._pf_attr)
            pf_list.insert(self._top_level_index, self.recipe)
        self.recipe.path = self._old_path

    @property
    def description(self) -> str:
        return f"Nest {self.recipe.item_id} in {self.fabricator.item_id}"


# ---------------------------------------------------------------------------
# Compound command (groups multiple commands into one undo step)
# ---------------------------------------------------------------------------


@dataclass
class CompoundCommand(EditCommand):
    """Groups multiple commands into a single undo/redo step.

    Execute runs all sub-commands in order. Undo reverses them in
    reverse order so that dependent state unwinds correctly.
    """

    commands: list[EditCommand]
    _description: str = "Compound edit"

    def execute(self) -> None:
        for cmd in self.commands:
            cmd.execute()

    def undo(self) -> None:
        for cmd in reversed(self.commands):
            cmd.undo()

    @property
    def description(self) -> str:
        return self._description
