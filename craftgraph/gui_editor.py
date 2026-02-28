"""Interactive node editor -- bridges GUI events to model commands.

Wraps ``RecipeNodeEditor`` (composition, not inheritance) and adds editing
capabilities: drag-and-drop wiring, inline field editing, context menus,
undo/redo, save to disk, and persistent node positions.

Every edit follows the same flow:

    1. GUI event -> resolve DPG IDs to model objects
    2. Create an ``EditCommand`` with references to mutable model objects
    3. ``EditHistory.execute(cmd)`` mutates the model
    4. ``refresh_visual()`` rebuilds the visual from the mutated model

Architecture notes:
    - This module DOES import DPG (it is part of the GUI layer).
    - All business logic lives in the commands (no DPG imports there).
    - The data model in ``models.py`` is the single source of truth.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import dearpygui.dearpygui as dpg
import networkx as nx

from craftgraph.commands import (
    AddIngredientCommand,
    AddNonRecipeCommand,
    AddRecipeCommand,
    ChangeIngredientCommand,
    ChangeNonRecipeFieldCommand,
    ChangeRecipeFieldCommand,
    CompoundCommand,
    EditCommand,
    EditHistory,
    NestRecipeInFabricatorCommand,
    NestTabInFabricatorCommand,
    RemoveIngredientCommand,
    RemoveNonRecipeCommand,
    RemoveRecipeCommand,
    UnnestRecipeFromFabricatorCommand,
    UnnestTabFromFabricatorCommand,
)
from craftgraph.graph import NodeType, build_graph, classify_nodes, find_cycles
from craftgraph.gui_autocomplete import AutocompletePopup
from craftgraph.gui_nodes import (
    KIND_TO_MODEL,
    KIND_TO_NON_RECIPE_MODEL,
    Link,
    NodeKind,
    RecipeNode,
    RecipeNodeEditor,
)
from craftgraph.layout_store import layout_path_for, load_layout, save_layout
from craftgraph.models import (
    AddedRecipe,
    AliasRecipe,
    BlockType,
    CraftingTab,
    CustomBioFuel,
    CustomFabricator,
    CustomFragmentCount,
    CustomSize,
    Ingredient,
    ModifiedRecipe,
    MovedRecipe,
    NonRecipeEntry,
    ParsedFile,
)
from craftgraph.serializer import serialize_file
from craftgraph.sprite_loader import resolve_sprite


class InteractiveNodeEditor:
    """Adds editing on top of the read-only ``RecipeNodeEditor``.

    One instance per file tab. Owns:
      - ``parsed_file``: the ParsedFile being edited
      - ``editor``: the underlying RecipeNodeEditor for visual display
      - ``history``: undo/redo stack for this file
      - ``item_id_registry``: set of all known ItemIDs (for autocomplete)
    """

    def __init__(
        self,
        parsed_file: ParsedFile,
        item_id_registry: set[str],
        on_dirty_change: object | None = None,
        vanilla_ids: frozenset[str] | None = None,
        sprite_lookup: dict[str, Path] | None = None,
    ) -> None:
        self.parsed_file = parsed_file
        self.editor = RecipeNodeEditor()
        self.history = EditHistory(on_change=self._on_history_change)
        self.item_id_registry = item_id_registry
        self._vanilla_ids = vanilla_ids
        self._sprite_lookup: dict[str, Path] = sprite_lookup or {}
        self._parent: int | str = 0
        self._status_callback: object | None = None
        self._on_dirty_change = on_dirty_change
        self._edit_window_id: int = 0
        self._context_menu_id: int = 0

        # Autocomplete for ItemID fields
        self._autocomplete = AutocompletePopup()
        self._autocomplete.set_items(item_id_registry, vanilla_ids=vanilla_ids)
        self._ac_anchor: int | str = 0

        # Current graph state (rebuilt on every refresh)
        self._graph: nx.DiGraph[str] = nx.DiGraph()
        self._classifications: dict[str, str] = {}
        self._cycles: list[list[str]] = []

        # Orphan ingredient nodes (not in the model, just visual).
        # Tracked so they survive visual rebuilds. Removed automatically
        # when their item_id becomes an actual graph ingredient.
        self._orphan_ingredients: dict[str, str] = {}  # key -> item_id

        # Manual sprite overrides (user-browsed images, not persisted).
        # Keyed by lowercase item_id.
        self._manual_sprites: dict[str, Path] = {}

        # DPG file_dialog widgets created by sprite browse sections.
        # Tracked for explicit cleanup since they are top-level DPG items.
        self._browse_dialog_ids: list[int] = []

    # -- Properties -----------------------------------------------------------

    @property
    def is_dirty(self) -> bool:
        return self.history.is_dirty

    @property
    def is_loaded(self) -> bool:
        return self.editor.is_loaded

    # -- Lifecycle ------------------------------------------------------------

    def load(self, parent: int | str) -> None:
        """Build the graph and populate the visual editor in the given container."""
        self._parent = parent
        self._rebuild_and_display()

    def clear(self) -> None:
        """Tear down all DPG widgets including cached textures."""
        self._close_edit_window()
        self._close_context_menu()
        self.editor.clear(keep_textures=False)

    # -- Visual refresh (the core rebuild loop) -------------------------------

    def refresh_visual(self) -> None:
        """Save positions, rebuild graph from model, reload visual."""
        saved_positions = self.editor.get_current_positions()
        self._rebuild_and_display(saved_positions=saved_positions)

    def _rebuild_and_display(
        self,
        saved_positions: dict[str, list[float]] | None = None,
    ) -> None:
        """Rebuild graph from parsed file and reload the node editor."""
        self._graph = build_graph([self.parsed_file])
        classifications = classify_nodes(self._graph)
        self._cycles = find_cycles(self._graph)

        # Build recipes_by_id map for back-references
        recipes_by_id: dict[str, ModifiedRecipe] = {}
        for recipe in self.parsed_file.all_recipes:
            recipes_by_id[recipe.item_id] = recipe

        # Try loading saved positions from disk if none provided
        if saved_positions is None:
            layout_data = self._load_positions_from_disk()
            if layout_data is not None:
                tab_key = Path(self.parsed_file.source_path).stem
                saved_positions = layout_data.get(tab_key)

        self.editor.load(
            self._graph,
            classifications,
            parent=self._parent,
            cycles=self._cycles,
            saved_positions=saved_positions,
            recipes_by_id=recipes_by_id,
            sprite_lookup=self._sprite_lookup,
            manual_sprites=self._manual_sprites,
        )

        # Re-spawn orphan ingredient nodes that survived the rebuild.
        # An orphan is removed once its item_id appears as a graph ingredient
        # (meaning it was wired to a recipe and is now part of the model).
        graph_ingredients: set[str] = set()
        for _src, tgt in self._graph.edges:
            graph_ingredients.add(tgt)

        surviving: dict[str, str] = {}
        for orphan_key, item_id in self._orphan_ingredients.items():
            if item_id in graph_ingredients:
                continue  # wired to a recipe, no longer an orphan
            pos = (
                saved_positions.get(orphan_key, [50.0, 50.0]) if saved_positions else [50.0, 50.0]
            )
            orphan = RecipeNode(
                item_id=item_id,
                node_type=NodeType.RAW_MATERIAL,
                kind=NodeKind.INGREDIENT,
                source_file="",
                ingredients=[],
                sprite_path=self._resolve_sprite(item_id),
            )
            orphan.create(
                self.editor._editor_id,
                pos,
                self.editor.theme,
                texture_cache=self.editor.texture_cache,
            )
            self.editor.nodes[orphan_key] = orphan
            self.editor._attr_to_node[orphan.output_attr] = (orphan, "__output__")
            for attr_name, attr_id in orphan.input_attrs.items():
                self.editor._attr_to_node[attr_id] = (orphan, attr_name)
            surviving[orphan_key] = item_id

        self._orphan_ingredients = surviving

        # Create visual nodes for non-recipe entries (standalone, not in the graph)
        self._spawn_non_recipe_nodes(saved_positions)

        # Re-apply interactive callbacks on the (newly created) editor widget.
        # RecipeNodeEditor.load() destroys and recreates the DPG node_editor,
        # so any previously configured callbacks are lost.
        if self.editor._editor_id and dpg.does_item_exist(self.editor._editor_id):
            dpg.configure_item(
                self.editor._editor_id,
                callback=self.on_link,
                delink_callback=self.on_delink,
            )

    def _on_history_change(self) -> None:
        """Called by EditHistory after every execute/undo/redo."""
        self.refresh_visual()

    # -- Model resolution helpers ---------------------------------------------

    def _find_recipe_in_model(self, item_id: str) -> ModifiedRecipe | None:
        """Search all recipe lists in the ParsedFile for a recipe by ItemID."""
        for recipe in self.parsed_file.all_recipes:
            if recipe.item_id == item_id:
                return recipe
        return None

    def _resolve_attr(self, attr_id: int) -> tuple[RecipeNode, str] | None:
        """Resolve a DPG attribute ID to its owning RecipeNode and role."""
        return self.editor._attr_to_node.get(attr_id)

    @staticmethod
    def _non_recipe_entry_id(entry: NonRecipeEntry) -> str:
        """Return the primary identifier for any non-recipe entry."""
        if isinstance(entry, CraftingTab):
            return entry.tab_id
        return entry.item_id

    def _resolve_sprite(self, item_id: str) -> Path | None:
        """Resolve sprite path: manual overrides, then auto-assign."""
        return resolve_sprite(item_id, self._manual_sprites, self._sprite_lookup)

    def _spawn_non_recipe_nodes(
        self,
        saved_positions: dict[str, list[float]] | None,
    ) -> None:
        """Create visual placeholder nodes for all non-recipe entries in the model.

        Handles two passes:
          1. Top-level non-recipe entries (fabricators, tabs, sizes, etc.)
          2. Nested fabricator contents (tabs, moved_recipes inside each fab)
             plus hierarchy links from fab -> tab -> recipe nodes.
        """
        entries: list[tuple[NodeKind, NonRecipeEntry]] = []

        for fab in self.parsed_file.custom_fabricators:
            entries.append((NodeKind.CUSTOM_FABRICATOR, fab))
        for tab in self.parsed_file.crafting_tabs:
            entries.append((NodeKind.CUSTOM_CRAFTING_TAB, tab))
        for mr in self.parsed_file.moved_recipes:
            entries.append((NodeKind.MOVED_RECIPE, mr))
        for cs in self.parsed_file.custom_sizes:
            entries.append((NodeKind.CUSTOM_SIZE, cs))
        for bf in self.parsed_file.custom_bio_fuels:
            entries.append((NodeKind.CUSTOM_BIO_FUEL, bf))
        for fc in self.parsed_file.custom_fragment_counts:
            entries.append((NodeKind.CUSTOM_FRAGMENT_COUNT, fc))

        if not entries:
            return

        source = str(self.parsed_file.source_path)
        for i, (kind, entry) in enumerate(entries):
            entry_id = self._non_recipe_entry_id(entry)
            node_key = f"{kind.value}::{entry_id}"

            # Avoid key collisions (e.g. duplicate ItemIDs within a type)
            if node_key in self.editor.nodes:
                node_key = f"{kind.value}::{entry_id}::{i}"

            default_y = 50.0 + i * 120.0
            pos = (
                saved_positions.get(node_key, [600.0, default_y])
                if saved_positions
                else [600.0, default_y]
            )

            node = RecipeNode(
                item_id=entry_id,
                node_type=NodeType.RAW_MATERIAL,
                kind=kind,
                source_file=source,
                ingredients=[],
                non_recipe=entry,
                sprite_path=self._resolve_sprite(entry_id),
            )
            node.create(
                self.editor._editor_id,
                pos,
                self.editor.theme,
                texture_cache=self.editor.texture_cache,
            )
            self.editor.nodes[node_key] = node
            self.editor._attr_to_node[node.output_attr] = (node, "__output__")
            for attr_name, attr_id in node.input_attrs.items():
                self.editor._attr_to_node[attr_id] = (node, attr_name)

        # Pass 2: spawn nested fabricator contents and create hierarchy links
        self._spawn_nested_fab_contents(saved_positions)

    def _spawn_nested_fab_contents(
        self,
        saved_positions: dict[str, list[float]] | None,
    ) -> None:
        """Spawn nested tabs/moved_recipes inside each fab, wire hierarchy links."""
        source = str(self.parsed_file.source_path)

        for fab in self.parsed_file.custom_fabricators:
            fab_key = f"{NodeKind.CUSTOM_FABRICATOR.value}::{fab.item_id}"
            fab_node = self.editor.nodes.get(fab_key)
            if fab_node is None:
                continue

            # Track tab nodes spawned for this fab (tab_id -> node)
            # so recipe hierarchy matching can look them up by path.
            tab_nodes: dict[str, RecipeNode] = {}

            # Spawn nested tabs
            for tab in fab.tabs:
                tab_key = f"{NodeKind.CUSTOM_CRAFTING_TAB.value}::{tab.tab_id}::fab::{fab.item_id}"
                if tab_key in self.editor.nodes:
                    tab_nodes[tab.tab_id] = self.editor.nodes[tab_key]
                    continue

                tab_node = self._spawn_nested_node(
                    tab_key,
                    tab.tab_id,
                    NodeKind.CUSTOM_CRAFTING_TAB,
                    source,
                    tab,
                    saved_positions,
                )
                tab_nodes[tab.tab_id] = tab_node
                self._create_hierarchy_link(fab_node, tab_node)

            # Spawn nested moved_recipes
            for mr in fab.moved_recipes:
                mr_key = f"{NodeKind.MOVED_RECIPE.value}::{mr.item_id}::fab::{fab.item_id}"
                if mr_key not in self.editor.nodes:
                    mr_node = self._spawn_nested_node(
                        mr_key,
                        mr.item_id,
                        NodeKind.MOVED_RECIPE,
                        source,
                        mr,
                        saved_positions,
                    )
                    self._create_hierarchy_link(fab_node, mr_node)

            # Wire hierarchy links from fab/tab to nested recipe nodes.
            # Nested recipes (added_recipes, alias_recipes, custom_foods)
            # are already spawned by RecipeNodeEditor.load() via all_recipes.
            # We just need to create the hierarchy link from the correct parent.
            nested_recipes: list[ModifiedRecipe] = []
            nested_recipes.extend(fab.added_recipes)
            nested_recipes.extend(fab.alias_recipes)
            nested_recipes.extend(fab.custom_foods)

            for recipe in nested_recipes:
                recipe_node = self.editor.nodes.get(recipe.item_id)
                if recipe_node is None:
                    continue
                parent_node = self._find_hierarchy_parent(
                    recipe,
                    fab_node,
                    tab_nodes,
                )
                self._create_hierarchy_link(parent_node, recipe_node)

    def _spawn_nested_node(
        self,
        node_key: str,
        entry_id: str,
        kind: NodeKind,
        source: str,
        entry: NonRecipeEntry,
        saved_positions: dict[str, list[float]] | None,
    ) -> RecipeNode:
        """Create a single nested non-recipe node and register it in the editor."""
        default_pos = [800.0, 50.0 + len(self.editor.nodes) * 120.0]
        pos = saved_positions.get(node_key, default_pos) if saved_positions else default_pos

        node = RecipeNode(
            item_id=entry_id,
            node_type=NodeType.RAW_MATERIAL,
            kind=kind,
            source_file=source,
            ingredients=[],
            non_recipe=entry,
            sprite_path=self._resolve_sprite(entry_id),
        )
        node.create(
            self.editor._editor_id,
            pos,
            self.editor.theme,
            texture_cache=self.editor.texture_cache,
        )
        self.editor.nodes[node_key] = node
        self.editor._attr_to_node[node.output_attr] = (node, "__output__")
        for attr_name, attr_id in node.input_attrs.items():
            self.editor._attr_to_node[attr_id] = (node, attr_name)
        return node

    def _create_hierarchy_link(
        self,
        parent_node: RecipeNode,
        child_node: RecipeNode,
    ) -> None:
        """Create a visual hierarchy link from parent's output to child's empty input.

        Connects ``parent_node.output_attr`` to the ``__empty__`` input pin on the
        child node, representing a containment relationship (fab -> tab, tab -> recipe).
        """
        target_attr = child_node.input_attrs.get("__empty__")
        if target_attr is None or not parent_node.output_attr:
            return

        link_id = int(
            dpg.add_node_link(
                parent_node.output_attr,
                target_attr,
                parent=self.editor._editor_id,
            )
        )
        self.editor.links.append(
            Link(
                source_attr=parent_node.output_attr,
                target_attr=target_attr,
                link_id=link_id,
            )
        )

    @staticmethod
    def _find_hierarchy_parent(
        recipe: ModifiedRecipe,
        fab_node: RecipeNode,
        tab_nodes: dict[str, RecipeNode],
    ) -> RecipeNode:
        """Determine the visual parent for a nested recipe based on its path.

        If the recipe has a ``path`` field (AddedRecipe/AliasRecipe/CustomFood),
        the last segment is matched against tab IDs spawned for this fabricator.
        Falls back to the fabricator node when no matching tab is found.
        """
        path = ""
        if isinstance(recipe, AddedRecipe):
            path = recipe.path

        if path:
            # The path is slash-separated (e.g. "FabId/TabId/SubTabId").
            # Match the last segment against known tab IDs for this fab.
            segments = path.rstrip("/").split("/")
            # Walk from deepest to shallowest segment to find the nearest tab
            for segment in reversed(segments):
                if segment in tab_nodes:
                    return tab_nodes[segment]

        return fab_node

    # -- Hierarchy connection dispatch ---------------------------------------

    def _find_fab_owning_tab(self, tab: CraftingTab) -> CustomFabricator | None:
        """Find the CustomFabricator that contains the given tab in its nested list."""
        for fab in self.parsed_file.custom_fabricators:
            if tab in fab.tabs:
                return fab
        return None

    def _try_hierarchy_link(
        self,
        source_node: RecipeNode,
        target_node: RecipeNode,
        source_role: str,
        target_role: str,
    ) -> EditCommand | None:
        """Attempt to interpret a drag-link as a hierarchy connection.

        Returns an ``EditCommand`` if the source/target pair represents a valid
        hierarchy relationship (fabricator->tab, fabricator->recipe, tab->recipe,
        tab->sub-tab).  Returns ``None`` for unrecognized patterns.
        """
        # Only handle output -> empty-input connections
        if source_role != "__output__" or target_role != "__empty__":
            return None

        # Reject self-connections
        if source_node is target_node:
            return None

        parent = source_node
        child = target_node

        if self.parsed_file.block_type == BlockType.CUSTOM_FABRICATORS:
            return self._try_fabricator_hierarchy(parent, child)

        return self._try_standalone_hierarchy(parent, child)

    def _try_fabricator_hierarchy(
        self,
        parent: RecipeNode,
        child: RecipeNode,
    ) -> EditCommand | None:
        """Handle hierarchy links inside a CustomFabricators file."""
        # Fabricator -> Tab
        if (
            parent.kind == NodeKind.CUSTOM_FABRICATOR
            and child.kind == NodeKind.CUSTOM_CRAFTING_TAB
            and isinstance(parent.non_recipe, CustomFabricator)
            and isinstance(child.non_recipe, CraftingTab)
        ):
            return NestTabInFabricatorCommand(
                parsed_file=self.parsed_file,
                fabricator=parent.non_recipe,
                tab=child.non_recipe,
            )

        # Fabricator -> Recipe (nest at fabricator root)
        if (
            parent.kind == NodeKind.CUSTOM_FABRICATOR
            and child.is_recipe
            and isinstance(parent.non_recipe, CustomFabricator)
            and isinstance(child.recipe, AddedRecipe)
        ):
            return NestRecipeInFabricatorCommand(
                parsed_file=self.parsed_file,
                fabricator=parent.non_recipe,
                recipe=child.recipe,
                path=parent.non_recipe.item_id,
            )

        # Tab -> Recipe (nest under tab's full path)
        if (
            parent.kind == NodeKind.CUSTOM_CRAFTING_TAB
            and child.is_recipe
            and isinstance(parent.non_recipe, CraftingTab)
            and isinstance(child.recipe, AddedRecipe)
        ):
            fab = self._find_fab_owning_tab(parent.non_recipe)
            if fab is None:
                return None
            tab_path = parent.non_recipe.tab_id
            if parent.non_recipe.parent_tab_path:
                tab_path = f"{parent.non_recipe.parent_tab_path}/{parent.non_recipe.tab_id}"
            full_path = f"{fab.item_id}/{tab_path}"
            return NestRecipeInFabricatorCommand(
                parsed_file=self.parsed_file,
                fabricator=fab,
                recipe=child.recipe,
                path=full_path,
            )

        # Tab -> Sub-tab (set child's parent_tab_path)
        if (
            parent.kind == NodeKind.CUSTOM_CRAFTING_TAB
            and child.kind == NodeKind.CUSTOM_CRAFTING_TAB
            and isinstance(parent.non_recipe, CraftingTab)
            and isinstance(child.non_recipe, CraftingTab)
        ):
            tab_path = parent.non_recipe.tab_id
            if parent.non_recipe.parent_tab_path:
                tab_path = f"{parent.non_recipe.parent_tab_path}/{parent.non_recipe.tab_id}"
            return ChangeNonRecipeFieldCommand(
                entry=child.non_recipe,
                field_name="parent_tab_path",
                new_value=tab_path,
            )

        # Fabricator -> Fabricator: reject
        return None

    def _try_standalone_hierarchy(
        self,
        parent: RecipeNode,
        child: RecipeNode,
    ) -> EditCommand | None:
        """Handle hierarchy links in standalone files (CustomCraftingTabs, etc.)."""
        # Tab -> Recipe (set recipe's path field)
        if (
            parent.kind == NodeKind.CUSTOM_CRAFTING_TAB
            and child.is_recipe
            and isinstance(parent.non_recipe, CraftingTab)
            and child.recipe is not None
        ):
            tab_path = parent.non_recipe.tab_id
            if parent.non_recipe.parent_tab_path:
                tab_path = f"{parent.non_recipe.parent_tab_path}/{parent.non_recipe.tab_id}"
            return ChangeRecipeFieldCommand(
                recipe=child.recipe,
                field_name="path",
                new_value=tab_path,
            )

        # Tab -> Sub-tab (set child's parent_tab_path)
        if (
            parent.kind == NodeKind.CUSTOM_CRAFTING_TAB
            and child.kind == NodeKind.CUSTOM_CRAFTING_TAB
            and isinstance(parent.non_recipe, CraftingTab)
            and isinstance(child.non_recipe, CraftingTab)
        ):
            tab_path = parent.non_recipe.tab_id
            if parent.non_recipe.parent_tab_path:
                tab_path = f"{parent.non_recipe.parent_tab_path}/{parent.non_recipe.tab_id}"
            return ChangeNonRecipeFieldCommand(
                entry=child.non_recipe,
                field_name="parent_tab_path",
                new_value=tab_path,
            )

        return None

    def _try_hierarchy_delink(
        self,
        source_node: RecipeNode,
        target_node: RecipeNode,
    ) -> EditCommand | None:
        """Attempt to reverse a hierarchy connection on delink.

        Returns an ``EditCommand`` that un-nests the child from the parent,
        or ``None`` if this link does not represent a hierarchy relationship.
        """
        parent = source_node
        child = target_node

        if self.parsed_file.block_type == BlockType.CUSTOM_FABRICATORS:
            return self._try_fabricator_hierarchy_delink(parent, child)

        return self._try_standalone_hierarchy_delink(parent, child)

    def _try_fabricator_hierarchy_delink(
        self,
        parent: RecipeNode,
        child: RecipeNode,
    ) -> EditCommand | None:
        """Handle hierarchy delinks inside a CustomFabricators file."""
        # Fabricator -> Tab (unnest tab from fabricator)
        if (
            parent.kind == NodeKind.CUSTOM_FABRICATOR
            and child.kind == NodeKind.CUSTOM_CRAFTING_TAB
            and isinstance(parent.non_recipe, CustomFabricator)
            and isinstance(child.non_recipe, CraftingTab)
            and child.non_recipe in parent.non_recipe.tabs
        ):
            return UnnestTabFromFabricatorCommand(
                parsed_file=self.parsed_file,
                fabricator=parent.non_recipe,
                tab=child.non_recipe,
            )

        # Fabricator/Tab -> Recipe (unnest recipe from fabricator)
        if parent.is_non_recipe and child.is_recipe and isinstance(child.recipe, AddedRecipe):
            if isinstance(parent.non_recipe, CustomFabricator):
                fab = parent.non_recipe
            elif isinstance(parent.non_recipe, CraftingTab):
                fab = self._find_fab_owning_tab(parent.non_recipe)
            else:
                return None
            if fab is None:
                return None
            return UnnestRecipeFromFabricatorCommand(
                parsed_file=self.parsed_file,
                fabricator=fab,
                recipe=child.recipe,
            )

        # Tab -> Sub-tab (clear child's parent_tab_path)
        if (
            parent.kind == NodeKind.CUSTOM_CRAFTING_TAB
            and child.kind == NodeKind.CUSTOM_CRAFTING_TAB
            and isinstance(child.non_recipe, CraftingTab)
        ):
            return ChangeNonRecipeFieldCommand(
                entry=child.non_recipe,
                field_name="parent_tab_path",
                new_value="",
            )

        return None

    def _try_standalone_hierarchy_delink(
        self,
        parent: RecipeNode,
        child: RecipeNode,
    ) -> EditCommand | None:
        """Handle hierarchy delinks in standalone files."""
        # Tab -> Recipe (clear recipe's path)
        if (
            parent.kind == NodeKind.CUSTOM_CRAFTING_TAB
            and child.is_recipe
            and child.recipe is not None
        ):
            return ChangeRecipeFieldCommand(
                recipe=child.recipe,
                field_name="path",
                new_value="",
            )

        # Tab -> Sub-tab (clear child's parent_tab_path)
        if (
            parent.kind == NodeKind.CUSTOM_CRAFTING_TAB
            and child.kind == NodeKind.CUSTOM_CRAFTING_TAB
            and isinstance(child.non_recipe, CraftingTab)
        ):
            return ChangeNonRecipeFieldCommand(
                entry=child.non_recipe,
                field_name="parent_tab_path",
                new_value="",
            )

        return None

    # -- Checkbox 1 + 2: Drag-and-drop wiring --------------------------------

    def on_link(self, sender: int, app_data: tuple[int, int]) -> None:
        """Handle a new link dragged by the user.

        Resolves source/target attributes to model objects and adds the
        source item as a new ingredient on the target recipe.

        When connecting to an occupied input pin, the link is swapped
        incrementally (UE5 blueprint style): the old link is severed,
        the old node stays in place as a disconnected orphan, and the
        dragged node gets linked instead.  No nodes are created or
        destroyed -- only the link moves.
        """
        source_attr_id, target_attr_id = app_data

        source_info = self._resolve_attr(source_attr_id)
        target_info = self._resolve_attr(target_attr_id)
        if source_info is None or target_info is None:
            return

        source_node, source_role = source_info
        target_node, target_role = target_info

        # Determine which direction the link was drawn and resolve the
        # ingredient item ID, target recipe, and any replaced ingredient.
        # Also track the visual nodes for incremental swap updates.
        ingredient_item_id: str | None = None
        target_recipe: ModifiedRecipe | None = None
        replaced_ingredient_id: str | None = None
        ingredient_visual_node: RecipeNode | None = None
        recipe_visual_node: RecipeNode | None = None

        if source_role == "__output__" and target_role != "__output__":
            # Dragged from an output pin to an input pin
            ingredient_item_id = source_node.item_id
            target_recipe = target_node.recipe
            replaced_ingredient_id = target_role
            ingredient_visual_node = source_node
            recipe_visual_node = target_node
        elif target_role == "__output__" and source_role != "__output__":
            # Dragged the other way (input to output)
            ingredient_item_id = target_node.item_id
            target_recipe = source_node.recipe
            replaced_ingredient_id = source_role
            ingredient_visual_node = target_node
            recipe_visual_node = source_node

        # Recipe-to-recipe output chaining (checkbox 2):
        # Both are output pins on crafted nodes -- always adds, no swap.
        if source_role == "__output__" and target_role == "__output__":
            replaced_ingredient_id = None
            if source_node.is_recipe and target_node.recipe is not None:
                ingredient_item_id = source_node.item_id
                target_recipe = target_node.recipe
            elif target_node.is_recipe and source_node.recipe is not None:
                ingredient_item_id = target_node.item_id
                target_recipe = source_node.recipe

        if target_recipe is None or ingredient_item_id is None:
            # Try hierarchy connection before giving up
            hierarchy_cmd = self._try_hierarchy_link(
                source_node,
                target_node,
                source_role,
                target_role,
            )
            if hierarchy_cmd is not None:
                self.history.execute(hierarchy_cmd)
            return

        # Validate: no self-loops
        if target_recipe.item_id == ingredient_item_id:
            return

        # Validate: no duplicate ingredients
        for existing in target_recipe.ingredients:
            if existing.item_id == ingredient_item_id:
                return

        # Pre-link cycle check (checkbox 9)
        if self._would_create_cycle(target_recipe.item_id, ingredient_item_id):
            self._show_cycle_warning(target_recipe.item_id, ingredient_item_id)
            return

        # Dynamic slot: dropping on the empty pin adds a new ingredient.
        # The full rebuild (via history.execute) recreates all pins from
        # the model, including a fresh __empty__ pin at the bottom.
        if replaced_ingredient_id == "__empty__":
            cmd = AddIngredientCommand(
                target_recipe,
                Ingredient(ingredient_item_id, 1),
            )
            self.history.execute(cmd)
            return

        # Swap: incremental visual update (no full rebuild).
        # Severs the old link, relabels the input pin, creates a new
        # link from the dragged node.  Both the old and new nodes
        # stay on the canvas -- only the connection changes.
        if (
            replaced_ingredient_id is not None
            and recipe_visual_node is not None
            and ingredient_visual_node is not None
        ):
            self._swap_link(
                target_recipe,
                replaced_ingredient_id,
                ingredient_item_id,
                recipe_visual_node,
                ingredient_visual_node,
            )
            return

        cmd = AddIngredientCommand(
            target_recipe,
            Ingredient(ingredient_item_id, 1),
        )
        self.history.execute(cmd)

    def _swap_link(
        self,
        recipe: ModifiedRecipe,
        old_ingredient_id: str,
        new_ingredient_id: str,
        recipe_visual_node: RecipeNode,
        ingredient_visual_node: RecipeNode,
    ) -> None:
        """Swap a link incrementally without a full visual rebuild.

        Mutates the model silently, severs the old DPG link, relabels
        the recipe's input pin, and wires a new link from the dragged
        node.  The previously connected node stays in place (orphaned).
        """
        # Find the ingredient index in the model
        for i, ing in enumerate(recipe.ingredients):
            if ing.item_id != old_ingredient_id:
                continue

            # 1. Model change (silent -- no rebuild callback)
            cmd = ChangeIngredientCommand(recipe, i, Ingredient(new_ingredient_id, 1))
            self.history.execute_silent(cmd)

            # Keep internal graph in sync for subsequent cycle checks
            self._graph = build_graph([self.parsed_file])
            self._cycles = find_cycles(self._graph)

            # 2. Find the input pin, sever its link, grey out the old node
            old_input_attr = recipe_visual_node.input_attrs.get(old_ingredient_id)
            if old_input_attr is None:
                return

            for link in self.editor.links[:]:
                if link.target_attr == old_input_attr:
                    dpg.delete_item(link.link_id)
                    self.editor.links.remove(link)
                    # Grey out whatever node was the source (now orphaned)
                    source_info = self.editor._attr_to_node.get(link.source_attr)
                    if source_info is not None:
                        orphaned_node, _ = source_info
                        dpg.bind_item_theme(
                            orphaned_node.dpg_tag,
                            self.editor.theme.get_unconnected(),
                        )
                    break

            # 3. Relabel the input pin and update tracking dicts
            del recipe_visual_node.input_attrs[old_ingredient_id]

            recipe_visual_node.input_attrs[new_ingredient_id] = old_input_attr
            self.editor._attr_to_node[old_input_attr] = (
                recipe_visual_node,
                new_ingredient_id,
            )

            # Update the text label on the input pin
            children = dpg.get_item_children(old_input_attr, 1)
            if children:
                dpg.set_value(children[0], f"{new_ingredient_id} x1")

            # Update the RecipeNode.ingredients snapshot
            for idx, (name, _req) in enumerate(recipe_visual_node.ingredients):
                if name == old_ingredient_id:
                    recipe_visual_node.ingredients[idx] = (new_ingredient_id, 1)
                    break

            # 4. Wire new link from the dragged node to the recipe
            link_id = int(
                dpg.add_node_link(
                    ingredient_visual_node.output_attr,
                    old_input_attr,
                    parent=self.editor._editor_id,
                )
            )
            self.editor.links.append(
                Link(
                    source_attr=ingredient_visual_node.output_attr,
                    target_attr=old_input_attr,
                    link_id=link_id,
                )
            )
            return

    def on_delink(self, sender: int, link_id: int) -> None:
        """Handle link deletion by the user (delink callback)."""
        # Find which link this is and remove the corresponding ingredient
        for link in self.editor.links:
            if link.link_id != link_id:
                continue

            source_info = self._resolve_attr(link.source_attr)
            target_info = self._resolve_attr(link.target_attr)
            if source_info is None or target_info is None:
                break

            # The target node (with input pin) is the recipe
            target_node, target_role = target_info
            source_node, _source_role = source_info

            if target_node.is_ingredient or target_role in ("__output__", "__empty__"):
                break

            # Hierarchy delink: source is non-recipe, target is non-recipe or recipe
            if source_node.is_non_recipe and (target_node.is_non_recipe or target_node.is_recipe):
                hierarchy_undo = self._try_hierarchy_delink(source_node, target_node)
                if hierarchy_undo is not None:
                    self.history.execute(hierarchy_undo)
                    return

            if target_node.recipe is None:
                break

            # Find the ingredient index by matching item_id
            ingredient_id = source_node.item_id
            for i, ing in enumerate(target_node.recipe.ingredients):
                if ing.item_id == ingredient_id:
                    cmd = RemoveIngredientCommand(target_node.recipe, index=i)
                    self.history.execute(cmd)
                    return
            break

    # -- Checkbox 9: Live cycle detection ------------------------------------

    def _would_create_cycle(self, recipe_id: str, ingredient_id: str) -> bool:
        """Test whether adding an edge would create a cycle."""
        test_graph = self._graph.copy()
        test_graph.add_edge(recipe_id, ingredient_id)
        try:
            nx.find_cycle(test_graph)
        except nx.NetworkXNoCycle:
            return False
        return True

    def _show_cycle_warning(self, recipe_id: str, ingredient_id: str) -> None:
        """Show a warning dialog when a link would create a cycle."""
        tag = "cycle_warning_dialog"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        with dpg.window(
            label="Circular Dependency Warning",
            tag=tag,
            modal=True,
            width=420,
            height=140,
            no_resize=True,
            no_collapse=True,
        ):
            dpg.add_text(
                f"Adding {ingredient_id} to {recipe_id} would create\n"
                "a circular dependency. Link not created."
            )
            dpg.add_spacer(height=8)
            dpg.add_button(
                label="OK",
                width=80,
                callback=lambda: dpg.delete_item(tag),
            )

    # -- Checkbox 3: Inline field editing ------------------------------------

    def on_double_click(self) -> None:
        """Handle double-click: open edit dialog for the selected node."""
        if not self.editor._editor_id:
            return

        selected_nodes = dpg.get_selected_nodes(self.editor._editor_id)
        if not selected_nodes:
            return

        node_id = selected_nodes[0]
        user_data = dpg.get_item_user_data(node_id)
        if not isinstance(user_data, RecipeNode) or user_data.is_ingredient:
            return

        if user_data.non_recipe is not None:
            self._open_non_recipe_edit_dialog(user_data.non_recipe, user_data)
        elif user_data.recipe is not None:
            self._open_edit_dialog(user_data.recipe)

    def _close_edit_window(self) -> None:
        self._autocomplete.hide()
        self._ac_anchor = 0
        # Destroy any file_dialog widgets created by sprite browse sections.
        # These are top-level DPG items, not children of the edit window.
        for dialog_id in self._browse_dialog_ids:
            if dpg.does_item_exist(dialog_id):
                dpg.delete_item(dialog_id)
        self._browse_dialog_ids.clear()
        if self._edit_window_id and dpg.does_item_exist(self._edit_window_id):
            dpg.delete_item(self._edit_window_id)
        self._edit_window_id = 0

    def _make_ac_callback(self, input_id: int | str) -> Callable[..., Any]:
        """Return a DPG callback that drives the autocomplete popup for *input_id*."""

        def _on_select(selected_id: str) -> None:
            if dpg.does_item_exist(input_id):
                dpg.set_value(input_id, selected_id)
            self._ac_anchor = 0

        def _cb(sender: int | str, app_data: object, user_data: object) -> None:
            # Guard: if the input or its parent dialog was destroyed, bail out.
            if not dpg.does_item_exist(input_id):
                self._autocomplete.hide()
                self._ac_anchor = 0
                return

            # If the anchor widget was destroyed between calls, reset state.
            if self._ac_anchor and not dpg.does_item_exist(self._ac_anchor):
                self._ac_anchor = 0
                self._autocomplete.hide()

            text = str(dpg.get_value(input_id)).strip()
            if len(text) >= 1:
                if self._ac_anchor == input_id and self._autocomplete.is_visible:
                    self._autocomplete.update_filter(text)
                else:
                    self._ac_anchor = input_id
                    self._autocomplete.show(input_id, text, _on_select)
            else:
                self._autocomplete.hide()
                self._ac_anchor = 0

        return _cb

    def _create_sprite_browse_section(
        self,
        item_id: str,
        parent: int | str,
    ) -> None:
        """Add Browse Image / Clear Image buttons to an edit dialog."""
        current_sprite = self._resolve_sprite(item_id)
        label = str(current_sprite.name) if current_sprite else "(none)"

        dpg.add_separator(parent=parent)
        with dpg.group(horizontal=True, parent=parent):
            dpg.add_text("Image:")
            sprite_label_id = dpg.add_text(label)

        _item_id = item_id
        _sprite_label = sprite_label_id
        _self = self

        def _on_file_selected(sender: int, app_data: dict) -> None:  # type: ignore[type-arg]
            selections = app_data.get("selections", {})
            if not selections:
                return
            chosen_path = Path(next(iter(selections.values())))
            if not chosen_path.exists():
                return
            _self._manual_sprites[_item_id.lower()] = chosen_path
            if dpg.does_item_exist(_sprite_label):
                dpg.set_value(_sprite_label, chosen_path.name)
            _self.refresh_visual()

        def _on_clear() -> None:
            key = _item_id.lower()
            if key in _self._manual_sprites:
                del _self._manual_sprites[key]
            if dpg.does_item_exist(_sprite_label):
                auto = _self._resolve_sprite(_item_id)
                dpg.set_value(_sprite_label, str(auto.name) if auto else "(none)")
            _self.refresh_visual()

        # Per-dialog file dialog (hidden, shown on Browse click).
        browse_dialog_tag: int
        with dpg.file_dialog(
            directory_selector=False,
            show=False,
            callback=_on_file_selected,
            width=600,
            height=400,
        ) as browse_dialog_tag:
            dpg.add_file_extension(".png", color=(0, 255, 0, 255))
            dpg.add_file_extension(".PNG", color=(0, 255, 0, 255))

        self._browse_dialog_ids.append(browse_dialog_tag)

        _browse_tag = browse_dialog_tag

        with dpg.group(horizontal=True, parent=parent):
            dpg.add_button(
                label="Browse Image...",
                callback=lambda: dpg.show_item(_browse_tag),
            )
            dpg.add_button(label="Clear Image", callback=lambda: _on_clear())

    def _open_edit_dialog(self, recipe: ModifiedRecipe) -> None:
        """Open a modal dialog for editing recipe fields."""
        self._close_edit_window()

        win_id: int
        with dpg.window(
            label=f"Edit: {recipe.item_id}",
            width=500,
            height=450,
            no_resize=False,
            no_collapse=True,
        ) as win_id:
            self._edit_window_id = win_id

            # ItemID
            item_id_input = dpg.add_input_text(
                label="ItemID",
                default_value=recipe.item_id,
                width=300,
                on_enter=False,
            )
            dpg.set_item_callback(item_id_input, self._make_ac_callback(item_id_input))

            # AmountCrafted
            amount_input = dpg.add_input_int(
                label="Amount Crafted",
                default_value=recipe.amount_crafted,
                min_value=1,
                min_clamped=True,
                width=150,
            )

            # ForceUnlockAtStart
            force_unlock_value = recipe.force_unlock_at_start is True
            force_unlock_input = dpg.add_checkbox(
                label="Force Unlock At Start",
                default_value=force_unlock_value,
            )

            # AliasRecipe-specific fields
            display_name_input: int | str = 0
            tooltip_input: int | str = 0
            path_input: int | str = 0
            sprite_item_id_input: int | str = 0
            if isinstance(recipe, AliasRecipe):
                display_name_input = dpg.add_input_text(
                    label="Display Name",
                    default_value=recipe.display_name,
                    width=300,
                )
                tooltip_input = dpg.add_input_text(
                    label="Tooltip",
                    default_value=recipe.tooltip,
                    width=300,
                )
                sprite_item_id_input = dpg.add_input_text(
                    label="Sprite ItemID",
                    default_value=recipe.sprite_item_id or "",
                    width=300,
                )
                dpg.set_item_callback(
                    sprite_item_id_input,
                    self._make_ac_callback(sprite_item_id_input),
                )
            if isinstance(recipe, AddedRecipe):
                path_input = dpg.add_input_text(
                    label="Path",
                    default_value=recipe.path,
                    width=300,
                )

            dpg.add_separator()
            dpg.add_text("Ingredients:")

            # Container for ingredient rows so we can dynamically add more.
            ing_group = dpg.add_group()

            # Per-ingredient rows: [ItemID] x [Amount]
            ing_inputs: list[tuple[int | str, int | str]] = []

            def _add_ingredient_row(item_id: str = "", required: int = 1) -> None:
                with dpg.group(horizontal=True, parent=ing_group):
                    ing_id_input = dpg.add_input_text(
                        default_value=item_id,
                        width=200,
                        hint="ItemID",
                        on_enter=False,
                    )
                    dpg.set_item_callback(ing_id_input, self._make_ac_callback(ing_id_input))
                    ing_amt_input = dpg.add_input_int(
                        default_value=required,
                        min_value=1,
                        min_clamped=True,
                        width=80,
                    )
                    ing_inputs.append((ing_id_input, ing_amt_input))

            for ing in recipe.ingredients:
                _add_ingredient_row(ing.item_id, ing.required)

            dpg.add_button(
                label="+ Add Ingredient",
                callback=lambda: _add_ingredient_row(),
            )

            self._create_sprite_browse_section(recipe.item_id, parent=win_id)

            dpg.add_spacer(height=10)

            # Capture references for the apply callback
            _recipe = recipe
            _item_id_input = item_id_input
            _amount_input = amount_input
            _force_unlock_input = force_unlock_input
            _display_name_input = display_name_input
            _tooltip_input = tooltip_input
            _sprite_item_id_input = sprite_item_id_input
            _path_input = path_input
            _ing_inputs = ing_inputs

            def _on_apply() -> None:
                cmds: list[object] = []

                # Scalar fields
                new_item_id = str(dpg.get_value(_item_id_input)).strip()
                if new_item_id and new_item_id != _recipe.item_id:
                    cmds.append(ChangeRecipeFieldCommand(_recipe, "item_id", new_item_id))

                new_amount = int(dpg.get_value(_amount_input))
                if new_amount != _recipe.amount_crafted:
                    cmds.append(ChangeRecipeFieldCommand(_recipe, "amount_crafted", new_amount))

                new_force = bool(dpg.get_value(_force_unlock_input))
                old_force = _recipe.force_unlock_at_start is True
                if new_force != old_force:
                    cmds.append(
                        ChangeRecipeFieldCommand(
                            _recipe,
                            "force_unlock_at_start",
                            True if new_force else None,
                        )
                    )

                # Alias fields
                if isinstance(_recipe, AliasRecipe) and _display_name_input:
                    new_dn = str(dpg.get_value(_display_name_input))
                    if new_dn != _recipe.display_name:
                        cmds.append(ChangeRecipeFieldCommand(_recipe, "display_name", new_dn))
                if isinstance(_recipe, AliasRecipe) and _tooltip_input:
                    new_tt = str(dpg.get_value(_tooltip_input))
                    if new_tt != _recipe.tooltip:
                        cmds.append(ChangeRecipeFieldCommand(_recipe, "tooltip", new_tt))
                if isinstance(_recipe, AliasRecipe) and _sprite_item_id_input:
                    raw_sid = str(dpg.get_value(_sprite_item_id_input)).strip()
                    new_sid: str | None = raw_sid if raw_sid else None
                    if new_sid != _recipe.sprite_item_id:
                        cmds.append(ChangeRecipeFieldCommand(_recipe, "sprite_item_id", new_sid))
                if isinstance(_recipe, AddedRecipe) and _path_input:
                    new_path = str(dpg.get_value(_path_input))
                    if new_path != _recipe.path:
                        cmds.append(ChangeRecipeFieldCommand(_recipe, "path", new_path))

                # Ingredient changes (existing) and additions (new rows)
                for idx, (id_input, amt_input) in enumerate(_ing_inputs):
                    new_id = str(dpg.get_value(id_input)).strip()
                    new_amt = int(dpg.get_value(amt_input))
                    if idx < len(_recipe.ingredients):
                        old_ing = _recipe.ingredients[idx]
                        if new_id != old_ing.item_id or new_amt != old_ing.required:
                            cmds.append(
                                ChangeIngredientCommand(_recipe, idx, Ingredient(new_id, new_amt))
                            )
                    elif new_id:
                        cmds.append(AddIngredientCommand(_recipe, Ingredient(new_id, new_amt)))

                if cmds:
                    compound = CompoundCommand(
                        commands=cmds,  # type: ignore[arg-type]
                        _description=f"Edit {_recipe.item_id}",
                    )
                    self.history.execute(compound)

                self._close_edit_window()

            with dpg.group(horizontal=True):
                dpg.add_button(label="Apply", width=100, callback=lambda: _on_apply())
                dpg.add_button(
                    label="Cancel",
                    width=100,
                    callback=lambda: self._close_edit_window(),
                )

    # -- Checkbox 5: Right-click context menu ---------------------------------

    def on_right_click(self, mouse_pos: tuple[float, float]) -> None:
        """Show a context menu at the mouse position."""
        self._close_context_menu()

        if not self.editor._editor_id:
            return

        # Check if a node is selected
        selected_nodes = dpg.get_selected_nodes(self.editor._editor_id)

        menu_id: int
        with dpg.window(
            no_title_bar=True,
            popup=True,
            width=200,
            min_size=[200, 30],
            pos=[int(mouse_pos[0]), int(mouse_pos[1])],
        ) as menu_id:
            self._context_menu_id = menu_id

            if selected_nodes:
                # Node context menu
                node_id = selected_nodes[0]
                user_data = dpg.get_item_user_data(node_id)
                if isinstance(user_data, RecipeNode) and user_data.is_recipe:
                    recipe = user_data.recipe
                    if recipe is not None:
                        dpg.add_menu_item(
                            label="Edit Fields...",
                            user_data=recipe,
                            callback=lambda s, a, u: self._ctx_edit_node(u),
                        )
                        dpg.add_menu_item(
                            label="Delete Recipe",
                            user_data=recipe,
                            callback=lambda s, a, u: self._ctx_delete_node(u),
                        )
                elif isinstance(user_data, RecipeNode) and user_data.is_non_recipe:
                    kind_label = user_data.kind.value.replace("_", " ").title()
                    dpg.add_text(f"{kind_label}: {user_data.item_id}")
                    dpg.add_separator()
                    if user_data.non_recipe is not None:
                        dpg.add_menu_item(
                            label="Edit Fields...",
                            user_data=user_data,
                            callback=lambda s, a, u: self._open_non_recipe_edit_dialog(
                                u.non_recipe, u
                            ),
                        )
                    dpg.add_menu_item(
                        label=f"Delete {kind_label}",
                        user_data=user_data,
                        callback=lambda s, a, u: self._ctx_delete_non_recipe(u),
                    )
                elif isinstance(user_data, RecipeNode) and user_data.is_ingredient:
                    dpg.add_text(f"Ingredient: {user_data.item_id}")
                    dpg.add_separator()
                    dpg.add_menu_item(
                        label="Edit Ingredient...",
                        user_data=user_data,
                        callback=lambda s, a, u: self._ctx_edit_ingredient(u),
                    )
                    dpg.add_menu_item(
                        label="Delete Ingredient",
                        user_data=user_data,
                        callback=lambda s, a, u: self._ctx_delete_ingredient(u),
                    )
                    with dpg.menu(label="Promote to Recipe"):
                        for _kind, (label, cls) in KIND_TO_MODEL.items():
                            dpg.add_menu_item(
                                label=label,
                                user_data=(user_data.item_id, cls),
                                callback=lambda s, a, u: self._ctx_promote_ingredient(u[0], u[1]),
                            )
            else:
                # Canvas context menu: spawn new nodes
                dpg.add_menu_item(
                    label="Add Ingredient",
                    callback=lambda s, a, u: self._ctx_add_ingredient(),
                )
                dpg.add_separator()
                with dpg.menu(label="Add Recipe"):
                    for _kind, (label, cls) in KIND_TO_MODEL.items():
                        dpg.add_menu_item(
                            label=label,
                            user_data=cls,
                            callback=lambda s, a, u: self._ctx_add_recipe(u),
                        )
                dpg.add_separator()
                dpg.add_menu_item(
                    label="Add Fabricator",
                    user_data=NodeKind.CUSTOM_FABRICATOR,
                    callback=lambda s, a, u: self._ctx_add_non_recipe(u),
                )
                dpg.add_menu_item(
                    label="Add Tab",
                    user_data=NodeKind.CUSTOM_CRAFTING_TAB,
                    callback=lambda s, a, u: self._ctx_add_non_recipe(u),
                )
                with dpg.menu(label="Add Property"):
                    dpg.add_menu_item(
                        label="Custom Size",
                        user_data=NodeKind.CUSTOM_SIZE,
                        callback=lambda s, a, u: self._ctx_add_non_recipe(u),
                    )
                    dpg.add_menu_item(
                        label="Custom BioFuel",
                        user_data=NodeKind.CUSTOM_BIO_FUEL,
                        callback=lambda s, a, u: self._ctx_add_non_recipe(u),
                    )
                    dpg.add_menu_item(
                        label="Fragment Count",
                        user_data=NodeKind.CUSTOM_FRAGMENT_COUNT,
                        callback=lambda s, a, u: self._ctx_add_non_recipe(u),
                    )
                    dpg.add_menu_item(
                        label="Moved Recipe",
                        user_data=NodeKind.MOVED_RECIPE,
                        callback=lambda s, a, u: self._ctx_add_non_recipe(u),
                    )

    def _close_context_menu(self) -> None:
        if self._context_menu_id and dpg.does_item_exist(self._context_menu_id):
            dpg.delete_item(self._context_menu_id)
        self._context_menu_id = 0

    def _ctx_edit_node(self, recipe: ModifiedRecipe) -> None:
        self._close_context_menu()
        self._open_edit_dialog(recipe)

    def _ctx_delete_node(self, recipe: ModifiedRecipe) -> None:
        self._close_context_menu()
        cmd = RemoveRecipeCommand(self.parsed_file, recipe)
        self.history.execute(cmd)

    def _ctx_delete_ingredient(self, ingredient_node: RecipeNode) -> None:
        """Delete an ingredient node (orphan or connected)."""
        self._close_context_menu()

        # If connected to a recipe, remove the ingredient from the model
        connection = self._find_recipe_for_ingredient(ingredient_node)
        if connection is not None:
            recipe_node, _role = connection
            if recipe_node.recipe is not None:
                for i, ing in enumerate(recipe_node.recipe.ingredients):
                    if ing.item_id == ingredient_node.item_id:
                        cmd = RemoveIngredientCommand(recipe_node.recipe, index=i)
                        self.history.execute(cmd)
                        return

        # Orphan ingredient: remove from tracking and rebuild
        for key, node in list(self.editor.nodes.items()):
            if node is ingredient_node:
                self._orphan_ingredients.pop(key, None)
                break
        self._rebuild_and_display()

    def _ctx_add_recipe(self, recipe_cls: type[ModifiedRecipe]) -> None:
        """Open a dialog to create a new recipe of the given type."""
        self._close_context_menu()

        tag = "add_recipe_dialog"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        with dpg.window(
            label="Add Recipe",
            tag=tag,
            width=350,
            height=120,
            no_resize=True,
            no_collapse=True,
        ):
            item_id_input = dpg.add_input_text(
                label="Item ID",
                width=200,
                hint="e.g. Titanium",
                on_enter=False,
            )
            dpg.set_item_callback(item_id_input, self._make_ac_callback(item_id_input))

            _cls = recipe_cls

            def _on_create() -> None:
                new_id = str(dpg.get_value(item_id_input)).strip()
                if not new_id:
                    return
                new_recipe = _cls(item_id=new_id)
                cmd = AddRecipeCommand(self.parsed_file, new_recipe)
                self.history.execute(cmd)
                self.item_id_registry.add(new_id)
                self._autocomplete.set_items(self.item_id_registry, vanilla_ids=self._vanilla_ids)
                self._autocomplete.hide()
                if dpg.does_item_exist(tag):
                    dpg.delete_item(tag)

            def _on_cancel() -> None:
                self._autocomplete.hide()
                self._ac_anchor = 0
                if dpg.does_item_exist(tag):
                    dpg.delete_item(tag)

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Create", width=80, callback=lambda: _on_create())
                dpg.add_button(
                    label="Cancel",
                    width=80,
                    callback=lambda: _on_cancel(),
                )

    def _ctx_edit_ingredient(self, ingredient_node: RecipeNode) -> None:
        """Open a mini dialog for editing an ingredient's ItemID and amount."""
        self._close_context_menu()

        connection = self._find_recipe_for_ingredient(ingredient_node)
        tag = "edit_ingredient_dialog"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        # If orphaned, find current amount from the connection; default to 1
        current_amount = 1
        if connection is not None:
            recipe_node, role = connection
            if recipe_node.recipe is not None:
                for ing in recipe_node.recipe.ingredients:
                    if ing.item_id == role:
                        current_amount = ing.required
                        break

        with dpg.window(
            label=f"Edit Ingredient: {ingredient_node.item_id}",
            tag=tag,
            width=350,
            height=250,
            no_resize=False,
            no_collapse=True,
        ) as ing_win_id:
            self._edit_window_id = ing_win_id

            item_id_input = dpg.add_input_text(
                label="Item ID",
                default_value=ingredient_node.item_id,
                width=200,
                on_enter=False,
            )
            dpg.set_item_callback(item_id_input, self._make_ac_callback(item_id_input))

            amount_input = dpg.add_input_int(
                label="Required",
                default_value=current_amount,
                min_value=1,
                min_clamped=True,
                width=100,
            )

            self._create_sprite_browse_section(
                ingredient_node.item_id,
                parent=ing_win_id,
            )

            _connection = connection

            def _on_apply() -> None:
                new_id = str(dpg.get_value(item_id_input)).strip()
                new_amt = int(dpg.get_value(amount_input))
                if not new_id:
                    return

                # Only update if connected to a recipe
                if _connection is not None:
                    recipe_node, role = _connection
                    if recipe_node.recipe is not None:
                        for i, ing in enumerate(recipe_node.recipe.ingredients):
                            if ing.item_id == role:
                                cmd = ChangeIngredientCommand(
                                    recipe_node.recipe,
                                    i,
                                    Ingredient(new_id, new_amt),
                                )
                                self.history.execute(cmd)
                                break

                self._close_edit_window()

            def _on_cancel() -> None:
                self._close_edit_window()

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Apply", width=80, callback=lambda: _on_apply())
                dpg.add_button(
                    label="Cancel",
                    width=80,
                    callback=lambda: _on_cancel(),
                )

    def _find_recipe_for_ingredient(
        self, ingredient_node: RecipeNode
    ) -> tuple[RecipeNode, str] | None:
        """Find the recipe node connected to an ingredient instance.

        Traverses editor links to find a link where the ingredient's output
        attribute is the source. Returns ``(recipe_node, ingredient_role)``
        or None if the ingredient is orphaned (no connection).
        """
        for link in self.editor.links:
            if link.source_attr != ingredient_node.output_attr:
                continue
            target_info = self._resolve_attr(link.target_attr)
            if target_info is not None:
                return target_info
        return None

    def _ctx_promote_ingredient(self, item_id: str, recipe_cls: type[ModifiedRecipe]) -> None:
        """Promote an ingredient to a full recipe of the given type."""
        self._close_context_menu()
        new_recipe = recipe_cls(item_id=item_id)
        cmd = AddRecipeCommand(self.parsed_file, new_recipe)
        self.history.execute(cmd)

    def _ctx_add_ingredient(self) -> None:
        """Open a dialog to spawn a standalone ingredient node on the canvas."""
        self._close_context_menu()

        tag = "add_ingredient_dialog"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        with dpg.window(
            label="Add Ingredient",
            tag=tag,
            width=350,
            height=100,
            no_resize=True,
            no_collapse=True,
        ):
            item_id_input = dpg.add_input_text(
                label="Item ID",
                width=200,
                hint="e.g. Titanium",
                on_enter=False,
            )
            dpg.set_item_callback(item_id_input, self._make_ac_callback(item_id_input))

            def _on_create() -> None:
                new_id = str(dpg.get_value(item_id_input)).strip()
                if not new_id:
                    return

                # Generate a unique key for the orphan ingredient
                counter = 0
                while f"orphan::{new_id}::{counter}" in self.editor.nodes:
                    counter += 1
                orphan_key = f"orphan::{new_id}::{counter}"

                orphan = RecipeNode(
                    item_id=new_id,
                    node_type=NodeType.RAW_MATERIAL,
                    kind=NodeKind.INGREDIENT,
                    source_file="",
                    ingredients=[],
                    sprite_path=self._resolve_sprite(new_id),
                )
                orphan.create(
                    self.editor._editor_id,
                    [50.0, 50.0],
                    self.editor.theme,
                    texture_cache=self.editor.texture_cache,
                )
                self.editor.nodes[orphan_key] = orphan
                self.editor._attr_to_node[orphan.output_attr] = (
                    orphan,
                    "__output__",
                )
                for attr_name, attr_id in orphan.input_attrs.items():
                    self.editor._attr_to_node[attr_id] = (orphan, attr_name)

                # Track so the orphan survives visual rebuilds
                self._orphan_ingredients[orphan_key] = new_id

                self.item_id_registry.add(new_id)
                self._autocomplete.set_items(self.item_id_registry, vanilla_ids=self._vanilla_ids)
                self._autocomplete.hide()
                self._ac_anchor = 0
                if dpg.does_item_exist(tag):
                    dpg.delete_item(tag)

            def _on_cancel() -> None:
                self._autocomplete.hide()
                self._ac_anchor = 0
                if dpg.does_item_exist(tag):
                    dpg.delete_item(tag)

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Create", width=80, callback=lambda: _on_create())
                dpg.add_button(
                    label="Cancel",
                    width=80,
                    callback=lambda: _on_cancel(),
                )

    # -- Non-recipe node context menu handlers --------------------------------

    def _ctx_add_non_recipe(self, kind: NodeKind) -> None:
        """Open a dialog to create a new non-recipe entry of the given kind."""
        self._close_context_menu()

        kind_info = KIND_TO_NON_RECIPE_MODEL.get(kind)
        if kind_info is None:
            return
        label, cls = kind_info
        is_tab = kind == NodeKind.CUSTOM_CRAFTING_TAB

        tag = "add_non_recipe_dialog"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        id_label = "Tab ID" if is_tab else "Item ID"
        id_hint = "e.g. MyCustomTab" if is_tab else "e.g. Titanium"

        with dpg.window(
            label=f"Add {label}",
            tag=tag,
            width=350,
            height=120,
            no_resize=True,
            no_collapse=True,
        ):
            item_id_input = dpg.add_input_text(
                label=id_label,
                width=200,
                hint=id_hint,
                on_enter=False,
            )
            dpg.set_item_callback(item_id_input, self._make_ac_callback(item_id_input))

            _cls = cls
            _is_tab = is_tab

            def _on_create() -> None:
                new_id = str(dpg.get_value(item_id_input)).strip()
                if not new_id:
                    return
                new_entry: NonRecipeEntry
                if _is_tab:  # noqa: SIM108
                    new_entry = CraftingTab(tab_id=new_id)
                else:
                    new_entry = _cls(item_id=new_id)  # type: ignore[call-arg]
                cmd = AddNonRecipeCommand(self.parsed_file, new_entry)
                self.history.execute(cmd)
                self.item_id_registry.add(new_id)
                self._autocomplete.set_items(self.item_id_registry, vanilla_ids=self._vanilla_ids)
                self._autocomplete.hide()
                if dpg.does_item_exist(tag):
                    dpg.delete_item(tag)

            def _on_cancel() -> None:
                self._autocomplete.hide()
                self._ac_anchor = 0
                if dpg.does_item_exist(tag):
                    dpg.delete_item(tag)

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Create", width=80, callback=lambda: _on_create())
                dpg.add_button(
                    label="Cancel",
                    width=80,
                    callback=lambda: _on_cancel(),
                )

    def _ctx_delete_non_recipe(self, node: RecipeNode) -> None:
        """Delete a non-recipe node from the model."""
        self._close_context_menu()
        if node.non_recipe is not None:
            cmd = RemoveNonRecipeCommand(self.parsed_file, node.non_recipe)
            self.history.execute(cmd)

    def _open_non_recipe_edit_dialog(self, entry: NonRecipeEntry, node: RecipeNode) -> None:
        """Open a modal dialog for editing non-recipe entry fields."""
        self._close_context_menu()
        self._close_edit_window()

        kind_label = node.kind.value.replace("_", " ").title()
        entry_id = self._non_recipe_entry_id(entry)

        win_id: int
        with dpg.window(
            label=f"Edit {kind_label}: {entry_id}",
            width=420,
            height=300,
            no_resize=False,
            no_collapse=True,
        ) as win_id:
            self._edit_window_id = win_id

            # Build fields based on concrete type.
            field_inputs: dict[str, int | str] = {}

            if isinstance(entry, CraftingTab):
                field_inputs["tab_id"] = dpg.add_input_text(
                    label="TabID",
                    default_value=entry.tab_id,
                    width=250,
                )
                dpg.set_item_callback(
                    field_inputs["tab_id"],
                    self._make_ac_callback(field_inputs["tab_id"]),
                )
                field_inputs["display_name"] = dpg.add_input_text(
                    label="Display Name",
                    default_value=entry.display_name,
                    width=250,
                )
                field_inputs["sprite_item_id"] = dpg.add_input_text(
                    label="Sprite ItemID",
                    default_value=entry.sprite_item_id or "",
                    width=250,
                )
                dpg.set_item_callback(
                    field_inputs["sprite_item_id"],
                    self._make_ac_callback(field_inputs["sprite_item_id"]),
                )
                field_inputs["parent_tab_path"] = dpg.add_input_text(
                    label="Parent Tab Path",
                    default_value=entry.parent_tab_path,
                    width=250,
                )

            elif isinstance(entry, MovedRecipe):
                field_inputs["item_id"] = dpg.add_input_text(
                    label="ItemID",
                    default_value=entry.item_id,
                    width=250,
                )
                dpg.set_item_callback(
                    field_inputs["item_id"],
                    self._make_ac_callback(field_inputs["item_id"]),
                )
                field_inputs["old_path"] = dpg.add_input_text(
                    label="Old Path",
                    default_value=entry.old_path or "",
                    width=250,
                )
                field_inputs["new_path"] = dpg.add_input_text(
                    label="New Path",
                    default_value=entry.new_path or "",
                    width=250,
                )
                field_inputs["copied"] = dpg.add_checkbox(
                    label="Copied",
                    default_value=entry.copied,
                )
                field_inputs["hidden"] = dpg.add_checkbox(
                    label="Hidden",
                    default_value=entry.hidden,
                )

            elif isinstance(entry, CustomSize):
                field_inputs["item_id"] = dpg.add_input_text(
                    label="ItemID",
                    default_value=entry.item_id,
                    width=250,
                )
                dpg.set_item_callback(
                    field_inputs["item_id"],
                    self._make_ac_callback(field_inputs["item_id"]),
                )
                field_inputs["width"] = dpg.add_input_int(
                    label="Width",
                    default_value=entry.width,
                    min_value=1,
                    max_value=6,
                    min_clamped=True,
                    max_clamped=True,
                    width=120,
                )
                field_inputs["height"] = dpg.add_input_int(
                    label="Height",
                    default_value=entry.height,
                    min_value=1,
                    max_value=6,
                    min_clamped=True,
                    max_clamped=True,
                    width=120,
                )

            elif isinstance(entry, CustomBioFuel):
                field_inputs["item_id"] = dpg.add_input_text(
                    label="ItemID",
                    default_value=entry.item_id,
                    width=250,
                )
                dpg.set_item_callback(
                    field_inputs["item_id"],
                    self._make_ac_callback(field_inputs["item_id"]),
                )
                field_inputs["energy"] = dpg.add_input_float(
                    label="Energy",
                    default_value=entry.energy,
                    min_value=0.0,
                    min_clamped=True,
                    width=150,
                )

            elif isinstance(entry, CustomFragmentCount):
                field_inputs["item_id"] = dpg.add_input_text(
                    label="ItemID",
                    default_value=entry.item_id,
                    width=250,
                )
                dpg.set_item_callback(
                    field_inputs["item_id"],
                    self._make_ac_callback(field_inputs["item_id"]),
                )
                field_inputs["fragments_to_scan"] = dpg.add_input_int(
                    label="Fragments To Scan",
                    default_value=entry.fragments_to_scan,
                    min_value=1,
                    min_clamped=True,
                    width=120,
                )

            elif isinstance(entry, CustomFabricator):
                field_inputs["item_id"] = dpg.add_input_text(
                    label="ItemID",
                    default_value=entry.item_id,
                    width=250,
                )
                dpg.set_item_callback(
                    field_inputs["item_id"],
                    self._make_ac_callback(field_inputs["item_id"]),
                )
                field_inputs["display_name"] = dpg.add_input_text(
                    label="Display Name",
                    default_value=entry.display_name,
                    width=250,
                )
                field_inputs["tooltip"] = dpg.add_input_text(
                    label="Tooltip",
                    default_value=entry.tooltip,
                    width=250,
                )
                field_inputs["model"] = dpg.add_combo(
                    label="Model",
                    items=["Fabricator", "Workbench", "MoonPool"],
                    default_value=entry.model,
                    width=180,
                )
                field_inputs["allowed_in_base"] = dpg.add_checkbox(
                    label="Allowed In Base",
                    default_value=entry.allowed_in_base,
                )
                field_inputs["allowed_in_cyclops"] = dpg.add_checkbox(
                    label="Allowed In Cyclops",
                    default_value=entry.allowed_in_cyclops,
                )

            self._create_sprite_browse_section(entry_id, parent=win_id)

            dpg.add_spacer(height=10)

            # Capture for closure
            _entry = entry
            _field_inputs = field_inputs

            def _on_apply() -> None:
                cmds: list[ChangeNonRecipeFieldCommand] = []

                for field_name, widget_id in _field_inputs.items():
                    raw_value = dpg.get_value(widget_id)

                    old_value = getattr(_entry, field_name)

                    # Coerce to match the field's type.
                    if isinstance(old_value, str | None):
                        new_value: object = str(raw_value).strip() if raw_value else ""
                        # For optional string fields, convert empty to None.
                        if old_value is None and new_value == "":
                            new_value = None
                    elif isinstance(old_value, bool):
                        new_value = bool(raw_value)
                    elif isinstance(old_value, int):
                        new_value = int(raw_value)
                    elif isinstance(old_value, float):
                        new_value = float(raw_value)
                    else:
                        new_value = raw_value

                    if new_value != old_value:
                        cmds.append(ChangeNonRecipeFieldCommand(_entry, field_name, new_value))

                if cmds:
                    compound = CompoundCommand(
                        commands=cmds,  # type: ignore[arg-type]
                        _description=f"Edit {self._non_recipe_entry_id(_entry)}",
                    )
                    self.history.execute(compound)

                self._close_edit_window()

            with dpg.group(horizontal=True):
                dpg.add_button(label="Apply", width=100, callback=lambda: _on_apply())
                dpg.add_button(
                    label="Cancel",
                    width=100,
                    callback=lambda: self._close_edit_window(),
                )

    # -- Checkbox 6: Delete nodes and connections -----------------------------

    def on_delete_key(self) -> None:
        """Handle Delete key: remove selected links and nodes."""
        if not self.editor._editor_id:
            return

        cmds: list[object] = []

        # Delete selected links first
        selected_links: list[int] = dpg.get_selected_links(self.editor._editor_id)  # type: ignore[assignment]
        for link_id in selected_links:
            for link in self.editor.links:
                if link.link_id != link_id:
                    continue
                target_info = self._resolve_attr(link.target_attr)
                source_info = self._resolve_attr(link.source_attr)
                if target_info is None or source_info is None:
                    break
                target_node, _role = target_info
                source_node, _src_role = source_info
                if target_node.is_ingredient:
                    break
                if target_node.recipe is None:
                    break
                for i, ing in enumerate(target_node.recipe.ingredients):
                    if ing.item_id == source_node.item_id:
                        cmds.append(RemoveIngredientCommand(target_node.recipe, index=i))
                        break
                break

        # Delete selected nodes (recipes + ingredients)
        orphans_removed = False
        selected_nodes = dpg.get_selected_nodes(self.editor._editor_id)
        for node_id in selected_nodes:
            user_data = dpg.get_item_user_data(node_id)
            if not isinstance(user_data, RecipeNode):
                continue
            if user_data.is_recipe and user_data.recipe is not None:
                cmds.append(RemoveRecipeCommand(self.parsed_file, user_data.recipe))
            elif user_data.is_ingredient:
                # Connected ingredient: remove from recipe model
                connection = self._find_recipe_for_ingredient(user_data)
                if connection is not None:
                    recipe_node, _role = connection
                    if recipe_node.recipe is not None:
                        for i, ing in enumerate(recipe_node.recipe.ingredients):
                            if ing.item_id == user_data.item_id:
                                cmds.append(RemoveIngredientCommand(recipe_node.recipe, index=i))
                                break
                else:
                    # Orphan ingredient: remove from tracking
                    for key, node in list(self.editor.nodes.items()):
                        if node is user_data:
                            self._orphan_ingredients.pop(key, None)
                            orphans_removed = True
                            break

        if cmds:
            compound = CompoundCommand(
                commands=cmds,  # type: ignore[arg-type]
                _description="Delete selection",
            )
            self.history.execute(compound)
        elif orphans_removed:
            self._rebuild_and_display()

    # -- Checkbox 7: Undo / Redo ---------------------------------------------

    def undo(self) -> None:
        self.history.undo()

    def redo(self) -> None:
        self.history.redo()

    # -- Checkbox 8: Save to disk --------------------------------------------

    def save(self) -> bool:
        """Serialize the parsed file and write to disk.

        Also saves node positions to the layout sidecar.
        Returns True on success.
        """
        text = serialize_file(self.parsed_file)
        source = Path(self.parsed_file.source_path)
        if source.exists():
            source.write_text(text, encoding="utf-8")
        else:
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(text, encoding="utf-8")

        self.history.mark_saved()
        self.save_positions()
        return True

    # -- Checkbox 10: Persistent node positions -------------------------------

    def save_positions(self) -> None:
        """Save current node positions to the layout sidecar file."""
        positions = self.editor.get_current_positions()
        if not positions:
            return

        layout_path = layout_path_for(Path(self.parsed_file.source_path))
        tab_key = Path(self.parsed_file.source_path).stem

        # Load existing layout data and merge this tab's positions
        existing = load_layout(layout_path)
        all_tabs = existing if existing is not None else {}
        all_tabs[tab_key] = positions
        save_layout(layout_path, all_tabs)

    def _load_positions_from_disk(self) -> dict[str, dict[str, list[float]]] | None:
        """Load layout data from the sidecar file."""
        return load_layout(layout_path_for(Path(self.parsed_file.source_path)))

    # -- Cycle info for status bar -------------------------------------------

    @property
    def cycle_count(self) -> int:
        return len(self._cycles)
