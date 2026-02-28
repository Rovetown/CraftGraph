"""Node editor components for the CraftGraph GUI.

Contains the class-based node editor architecture:
- NodeKind: semantic enum for visual node classification
- NodeTheme: cached DPG themes by NodeType and NodeKind
- RecipeNode: dataclass wrapping a DPG node for one recipe/item
- Link: dataclass tracking a visual connection
- RecipeNodeEditor: manages the full editor lifecycle
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import dearpygui.dearpygui as dpg
import networkx as nx

from craftgraph.graph import NodeType
from craftgraph.models import (
    AddedRecipe,
    AliasRecipe,
    CraftingTab,
    CustomBioFuel,
    CustomFabricator,
    CustomFood,
    CustomFragmentCount,
    CustomSize,
    ModifiedRecipe,
    MovedRecipe,
    NonRecipeEntry,
)
from craftgraph.sprite_loader import resolve_sprite

# -- Node kind classification -------------------------------------------------


class NodeKind(Enum):
    """Semantic kind of a visual node in the editor.

    Distinct from NodeType (graph topology: RAW_MATERIAL/INTERMEDIATE/END_PRODUCT).
    NodeKind answers "what CC3 concept does this node represent?" while NodeType
    answers "where does this item sit in the dependency chain?"
    """

    INGREDIENT = "ingredient"
    MODIFIED_RECIPE = "modified_recipe"
    ADDED_RECIPE = "added_recipe"
    ALIAS_RECIPE = "alias_recipe"
    CUSTOM_FOOD = "custom_food"
    CUSTOM_FABRICATOR = "custom_fabricator"
    CUSTOM_CRAFTING_TAB = "custom_crafting_tab"
    MOVED_RECIPE = "moved_recipe"
    CUSTOM_SIZE = "custom_size"
    CUSTOM_BIO_FUEL = "custom_bio_fuel"
    CUSTOM_FRAGMENT_COUNT = "custom_fragment_count"


RECIPE_KINDS: frozenset[NodeKind] = frozenset(
    {
        NodeKind.MODIFIED_RECIPE,
        NodeKind.ADDED_RECIPE,
        NodeKind.ALIAS_RECIPE,
        NodeKind.CUSTOM_FOOD,
    }
)


def kind_from_recipe(recipe: ModifiedRecipe) -> NodeKind:
    """Determine NodeKind from a recipe's concrete type (most-derived first).

    Uses ``type(recipe) is`` (exact match) not ``isinstance`` to avoid
    parent-class matches in the ModifiedRecipe hierarchy.
    """
    if type(recipe) is CustomFood:
        return NodeKind.CUSTOM_FOOD
    if type(recipe) is AliasRecipe:
        return NodeKind.ALIAS_RECIPE
    if type(recipe) is AddedRecipe:
        return NodeKind.ADDED_RECIPE
    return NodeKind.MODIFIED_RECIPE


KIND_TO_MODEL: dict[NodeKind, tuple[str, type[ModifiedRecipe]]] = {
    NodeKind.MODIFIED_RECIPE: ("Modified Recipe", ModifiedRecipe),
    NodeKind.ADDED_RECIPE: ("Added Recipe", AddedRecipe),
    NodeKind.ALIAS_RECIPE: ("Alias Recipe", AliasRecipe),
    NodeKind.CUSTOM_FOOD: ("Custom Food", CustomFood),
}

NON_RECIPE_KINDS: frozenset[NodeKind] = frozenset(
    {
        NodeKind.CUSTOM_FABRICATOR,
        NodeKind.CUSTOM_CRAFTING_TAB,
        NodeKind.MOVED_RECIPE,
        NodeKind.CUSTOM_SIZE,
        NodeKind.CUSTOM_BIO_FUEL,
        NodeKind.CUSTOM_FRAGMENT_COUNT,
    }
)

KIND_TO_NON_RECIPE_MODEL: dict[NodeKind, tuple[str, type[NonRecipeEntry]]] = {
    NodeKind.CUSTOM_FABRICATOR: ("Custom Fabricator", CustomFabricator),
    NodeKind.CUSTOM_CRAFTING_TAB: ("Crafting Tab", CraftingTab),
    NodeKind.MOVED_RECIPE: ("Moved Recipe", MovedRecipe),
    NodeKind.CUSTOM_SIZE: ("Custom Size", CustomSize),
    NodeKind.CUSTOM_BIO_FUEL: ("Custom BioFuel", CustomBioFuel),
    NodeKind.CUSTOM_FRAGMENT_COUNT: ("Fragment Count", CustomFragmentCount),
}

_RECIPE_TYPE_STR_TO_KIND: dict[str, NodeKind] = {
    "ModifiedRecipe": NodeKind.MODIFIED_RECIPE,
    "AddedRecipe": NodeKind.ADDED_RECIPE,
    "AliasRecipe": NodeKind.ALIAS_RECIPE,
    "CustomFood": NodeKind.CUSTOM_FOOD,
}

# -- Theme colors by node classification ---------------------------------------
# Darkened for readable white text on the title bar.

_NODE_COLORS: dict[NodeType, tuple[int, int, int]] = {
    NodeType.RAW_MATERIAL: (34, 139, 80),  # forest green
    NodeType.INTERMEDIATE: (41, 105, 155),  # steel blue
    NodeType.END_PRODUCT: (178, 142, 16),  # dark gold
}

_KIND_COLORS: dict[NodeKind, tuple[int, int, int]] = {
    NodeKind.MODIFIED_RECIPE: (41, 105, 155),  # steel blue
    NodeKind.ADDED_RECIPE: (50, 130, 90),  # teal green
    NodeKind.ALIAS_RECIPE: (140, 80, 160),  # muted purple
    NodeKind.CUSTOM_FOOD: (178, 110, 40),  # warm orange
    NodeKind.CUSTOM_FABRICATOR: (175, 95, 85),  # salmon/coral
    NodeKind.CUSTOM_CRAFTING_TAB: (95, 95, 140),  # slate/lavender
    NodeKind.MOVED_RECIPE: (110, 110, 110),  # muted gray
    NodeKind.CUSTOM_SIZE: (60, 145, 135),  # light teal
    NodeKind.CUSTOM_BIO_FUEL: (90, 150, 45),  # lime
    NodeKind.CUSTOM_FRAGMENT_COUNT: (155, 95, 105),  # dusty rose
}

_CYCLE_COLOR: tuple[int, int, int] = (170, 50, 40)  # dark red
_UNCONNECTED_COLOR: tuple[int, int, int] = (90, 90, 90)  # gray
_DEFAULT_COLOR: tuple[int, int, int] = (100, 100, 100)


# -- Theme cache ---------------------------------------------------------------


class NodeTheme:
    """Cached DPG themes for node title bar and link colors.

    Creates each theme once on first access, then returns
    the cached DPG theme ID on subsequent calls. Supports
    NodeType-based themes plus special themes for cycle
    participants and unconnected nodes.
    """

    def __init__(self) -> None:
        self._cache: dict[str, int] = {}

    def get(self, node_type: NodeType) -> int:
        """Return the DPG theme ID for the given node type (topology-based)."""
        return self._ensure_node_theme(
            node_type.value, _NODE_COLORS.get(node_type, _DEFAULT_COLOR)
        )

    def get_kind(self, kind: NodeKind) -> int:
        """Return the DPG theme ID for the given node kind (recipe-type-based)."""
        key = f"kind_{kind.value}"
        return self._ensure_node_theme(key, _KIND_COLORS.get(kind, _DEFAULT_COLOR))

    def get_cycle(self) -> int:
        """Red theme for nodes participating in circular dependencies."""
        return self._ensure_node_theme("cycle", _CYCLE_COLOR)

    def get_unconnected(self) -> int:
        """Gray theme for isolated nodes with no connections."""
        return self._ensure_node_theme("unconnected", _UNCONNECTED_COLOR)

    def get_cycle_link(self) -> int:
        """Red theme for links that are part of a circular dependency."""
        cached = self._cache.get("cycle_link")
        if cached is not None:
            return cached

        theme_id: int
        with dpg.theme() as theme_id, dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(
                dpg.mvNodeCol_Link,
                _CYCLE_COLOR,
                category=dpg.mvThemeCat_Nodes,
            )
            dpg.add_theme_color(
                dpg.mvNodeCol_LinkHovered,
                tuple(min(c + 20, 255) for c in _CYCLE_COLOR),
                category=dpg.mvThemeCat_Nodes,
            )
            dpg.add_theme_color(
                dpg.mvNodeCol_LinkSelected,
                tuple(min(c + 40, 255) for c in _CYCLE_COLOR),
                category=dpg.mvThemeCat_Nodes,
            )
        self._cache["cycle_link"] = theme_id
        return theme_id

    def _ensure_node_theme(self, key: str, color: tuple[int, int, int]) -> int:
        """Create or return a cached node theme for the given color."""
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        theme_id: int
        with dpg.theme() as theme_id, dpg.theme_component(dpg.mvNode):
            dpg.add_theme_color(
                dpg.mvNodeCol_TitleBar,
                color,
                category=dpg.mvThemeCat_Nodes,
            )
            dpg.add_theme_color(
                dpg.mvNodeCol_TitleBarHovered,
                tuple(min(c + 15, 255) for c in color),
                category=dpg.mvThemeCat_Nodes,
            )
            dpg.add_theme_color(
                dpg.mvNodeCol_TitleBarSelected,
                tuple(min(c + 30, 255) for c in color),
                category=dpg.mvThemeCat_Nodes,
            )
        self._cache[key] = theme_id
        return theme_id


# -- Data classes --------------------------------------------------------------


@dataclass
class Link:
    """Tracks a visual connection between two node attributes."""

    source_attr: int
    target_attr: int
    link_id: int


@dataclass
class RecipeNode:
    """Visual representation of a recipe/item in the DPG node editor.

    Each RecipeNode wraps a single DPG node widget. The class instance
    is stored as ``user_data`` on the DPG node, allowing recovery via
    ``dpg.get_item_user_data(node_id)``.

    The node displays:
    - Title bar: ItemID (set as node label)
    - Output attribute (right pin): recipe type and ingredient count
    - Input attributes (left pins): one per ingredient, labeled with ID and amount
    """

    item_id: str
    node_type: NodeType
    kind: NodeKind
    source_file: str
    ingredients: list[tuple[str, int]] = field(default_factory=list)
    dpg_tag: int = 0
    output_attr: int = 0
    input_attrs: dict[str, int] = field(default_factory=dict)
    hierarchy_input_attr: int = 0
    recipe: ModifiedRecipe | None = None
    non_recipe: NonRecipeEntry | None = None
    sprite_path: Path | None = None

    @property
    def is_recipe(self) -> bool:
        """True when this node represents a crafted recipe (any recipe kind)."""
        return self.kind in RECIPE_KINDS

    @property
    def is_ingredient(self) -> bool:
        """True when this node is a raw/intermediate ingredient instance."""
        return self.kind == NodeKind.INGREDIENT

    @property
    def is_non_recipe(self) -> bool:
        """True when this node is a non-recipe CC3 entry (fabricator, tab, property)."""
        return self.kind in NON_RECIPE_KINDS

    def create(
        self,
        editor: int,
        pos: list[float],
        theme: NodeTheme,
        texture_cache: TextureCache | None = None,
    ) -> None:
        """Build the DPG node inside the given node editor."""
        node_id: int
        with dpg.node(
            label=self.item_id,
            pos=[int(pos[0]), int(pos[1])],
            parent=editor,
            user_data=self,
        ) as node_id:
            # Output attribute: recipe type + ingredient count (pin on right)
            out_attr: int
            with dpg.node_attribute(
                attribute_type=dpg.mvNode_Attr_Output,
            ) as out_attr:
                dpg.add_text(self._build_type_label())
            self.output_attr = out_attr

            # Sprite thumbnail (static, no pin)
            if self.sprite_path is not None and texture_cache is not None:
                tex_tag = texture_cache.get_or_load(self.sprite_path)
                if tex_tag is not None:
                    cfg = dpg.get_item_configuration(tex_tag)
                    orig_w = int(cfg.get("width", _THUMB_SIZE))
                    orig_h = int(cfg.get("height", _THUMB_SIZE))
                    dw, dh = _thumb_dimensions(orig_w, orig_h)
                    with dpg.node_attribute(
                        attribute_type=dpg.mvNode_Attr_Static,
                    ):
                        dpg.add_image(tex_tag, width=dw, height=dh)

            if self.is_non_recipe:
                # Static attributes showing field info (no pins)
                for line in self._non_recipe_info_lines():
                    with dpg.node_attribute(
                        attribute_type=dpg.mvNode_Attr_Static,
                    ):
                        dpg.add_text(line)
            else:
                # Input attributes: one per ingredient (pins on left)
                for ing_id, required in self.ingredients:
                    in_attr: int
                    with dpg.node_attribute(
                        attribute_type=dpg.mvNode_Attr_Input,
                    ) as in_attr:
                        dpg.add_text(f"{ing_id} x{required}")
                    self.input_attrs[ing_id] = in_attr

            # Hierarchy input pin: connection point for parent containment
            # links (fabricator -> tab, tab -> recipe). Separate from the
            # __empty__ pin so hierarchy links don't consume the drop target.
            if not self.is_ingredient:
                hier_in: int
                with dpg.node_attribute(
                    attribute_type=dpg.mvNode_Attr_Input,
                ) as hier_in:
                    dpg.add_text("")  # invisible label, just a pin
                self.hierarchy_input_attr = hier_in

            # Always-present empty input pin (UE5-style dynamic slots).
            # Recipe nodes: drop target for adding new ingredients.
            # Non-recipe/ingredient nodes: default input connection point.
            empty_in: int
            with dpg.node_attribute(
                attribute_type=dpg.mvNode_Attr_Input,
            ) as empty_in:
                label = "+ drop ingredient" if self.is_recipe else self.item_id
                dpg.add_text(label)
            self.input_attrs["__empty__"] = empty_in

        self.dpg_tag = node_id
        if self.is_ingredient:
            dpg.bind_item_theme(node_id, theme.get(self.node_type))
        else:
            dpg.bind_item_theme(node_id, theme.get_kind(self.kind))

    def _build_type_label(self) -> str:
        """Build the display label for the output attribute."""
        if self.is_recipe:
            label = self.kind.value.replace("_", " ").title()
            if self.ingredients:
                return f"{label} ({len(self.ingredients)})"
            return label
        if self.is_non_recipe:
            return self.kind.value.replace("_", " ").title()
        return self.node_type.value.replace("_", " ").title()

    def _non_recipe_info_lines(self) -> list[str]:
        """Build display lines for non-recipe node fields."""
        nr = self.non_recipe
        if nr is None:
            return []
        if isinstance(nr, CustomFabricator):
            recipe_count = len(nr.added_recipes) + len(nr.alias_recipes) + len(nr.custom_foods)
            lines = [f"Model: {nr.model}"]
            if recipe_count:
                lines.append(f"Recipes: {recipe_count}")
            return lines
        if isinstance(nr, CraftingTab):
            tab_lines: list[str] = []
            if nr.display_name:
                tab_lines.append(f"Name: {nr.display_name}")
            if nr.parent_tab_path:
                tab_lines.append(f"Path: {nr.parent_tab_path}")
            return tab_lines or ["(empty tab)"]
        if isinstance(nr, MovedRecipe):
            if nr.hidden:
                return ["Hidden"]
            move_lines: list[str] = []
            if nr.old_path:
                move_lines.append(f"From: {nr.old_path}")
            if nr.new_path:
                move_lines.append(f"To: {nr.new_path}")
            if nr.copied:
                move_lines.append("(Copy)")
            return move_lines or ["(no path set)"]
        if isinstance(nr, CustomSize):
            return [f"{nr.width} x {nr.height}"]
        if isinstance(nr, CustomBioFuel):
            return [f"Energy: {nr.energy}"]
        if isinstance(nr, CustomFragmentCount):
            return [f"Fragments: {nr.fragments_to_scan}"]
        return []


# -- Texture cache for node sprites -------------------------------------------

_THUMB_SIZE = 48  # Display size in pixels for sprite thumbnails


class TextureCache:
    """Manages DPG texture loading and caching for node sprites.

    Each unique PNG path gets one DPG static texture, shared by all nodes
    referencing that image. Call ``clear()`` to destroy all textures and
    the texture registry when the editor is torn down.
    """

    def __init__(self) -> None:
        self._registry_id: int = 0
        self._cache: dict[Path, int] = {}  # path -> DPG texture tag

    def _ensure_registry(self) -> int:
        """Create the DPG texture registry on first use."""
        if not self._registry_id or not dpg.does_item_exist(self._registry_id):
            self._registry_id = dpg.add_texture_registry()
        return self._registry_id

    def get_or_load(self, sprite_path: Path) -> int | None:
        """Return DPG texture tag for the given PNG, loading it if needed.

        Returns None if the image cannot be loaded (missing file, corrupt, etc.).
        """
        if sprite_path in self._cache:
            tag = self._cache[sprite_path]
            if dpg.does_item_exist(tag):
                return tag
            # Stale cache entry -- reload
            del self._cache[sprite_path]

        if not sprite_path.exists():
            return None

        result = dpg.load_image(str(sprite_path))
        if result is None:
            return None

        width, height, _channels, data = result
        registry = self._ensure_registry()
        tag = dpg.add_static_texture(
            width=width,
            height=height,
            default_value=data,
            parent=registry,
        )
        self._cache[sprite_path] = tag
        return tag

    def clear(self) -> None:
        """Destroy all cached textures and the registry."""
        if self._registry_id and dpg.does_item_exist(self._registry_id):
            dpg.delete_item(self._registry_id, children_only=False)
        self._registry_id = 0
        self._cache.clear()

    @property
    def loaded_count(self) -> int:
        return len(self._cache)


def _thumb_dimensions(orig_w: int, orig_h: int, thumb_size: int = _THUMB_SIZE) -> tuple[int, int]:
    """Compute display dimensions preserving aspect ratio within thumb_size."""
    if orig_w <= 0 or orig_h <= 0:
        return thumb_size, thumb_size
    if orig_w >= orig_h:
        display_w = thumb_size
        display_h = max(1, int(thumb_size * orig_h / orig_w))
    else:
        display_h = thumb_size
        display_w = max(1, int(thumb_size * orig_w / orig_h))
    return display_w, display_h


# -- Node editor manager -------------------------------------------------------


class RecipeNodeEditor:
    """Manages the full DPG node editor: nodes, links, layout, and themes.

    The editor is built inside a parent container (typically a child_window).
    Call ``load()`` to populate from a NetworkX graph, and ``clear()`` to reset.
    """

    def __init__(self) -> None:
        self.theme = NodeTheme()
        self.nodes: dict[str, RecipeNode] = {}
        self.links: list[Link] = []
        self._editor_id: int = 0
        self._graph: nx.DiGraph[str] | None = None
        self.texture_cache = TextureCache()
        # Reverse map: DPG attribute ID -> (owning RecipeNode, role).
        # Role is an ingredient item_id for input attrs, or "__output__"
        # for output attrs. Populated during load().
        self._attr_to_node: dict[int, tuple[RecipeNode, str]] = {}

    def _link_callback(self, sender: int, app_data: tuple[int, int]) -> None:
        link_id = int(dpg.add_node_link(app_data[0], app_data[1], parent=sender))
        self.links.append(
            Link(
                source_attr=app_data[0],
                target_attr=app_data[1],
                link_id=link_id,
            )
        )

    def _delink_callback(self, _sender: int, app_data: int) -> None:
        dpg.delete_item(app_data)
        self.links = [lk for lk in self.links if lk.link_id != app_data]

    @property
    def is_loaded(self) -> bool:
        """Whether the editor has any nodes loaded."""
        return len(self.nodes) > 0

    def clear(self, keep_textures: bool = True) -> None:
        """Remove the node editor widget.

        Textures are preserved by default so they survive visual rebuilds
        (same PNGs reloaded from cache on the next ``load()``). Pass
        ``keep_textures=False`` to destroy textures too (tab close).
        """
        if self._editor_id and dpg.does_item_exist(self._editor_id):
            dpg.delete_item(self._editor_id)
        self._editor_id = 0
        self.nodes.clear()
        self.links.clear()
        self._attr_to_node.clear()
        self._graph = None
        if not keep_textures:
            self.texture_cache.clear()

    def load(
        self,
        graph: nx.DiGraph[str],
        classifications: dict[str, NodeType],
        parent: int | str,
        cycles: list[list[str]] | None = None,
        saved_positions: dict[str, list[float]] | None = None,
        recipes_by_id: dict[str, ModifiedRecipe] | None = None,
        sprite_lookup: dict[str, Path] | None = None,
        manual_sprites: dict[str, Path] | None = None,
    ) -> None:
        """Create nodes and links from a NetworkX graph.

        Uses instance-per-usage layout: each ingredient usage gets its own
        visual node (like UE5 material editor). Recipe nodes have input pins
        for each ingredient; ingredient instance nodes have a single output
        pin. Links connect each instance to its recipe's input.

        Applies visual overrides: red for cycle participants, gray for
        unconnected recipe nodes (no ingredients).

        If ``saved_positions`` is provided, those positions are used instead
        of the computed layout (for any node keys present in the dict).

        If ``recipes_by_id`` is provided, crafted recipe nodes get a
        back-reference to the actual model object for editing support.
        """
        self.clear()
        self._graph = graph

        # Always create the node editor widget so the user can interact
        # (right-click to add recipes, drag-and-drop) even when the graph
        # starts empty (e.g. fabricator-only files with no recipes yet).
        editor: int
        with dpg.node_editor(
            parent=parent,
            callback=self._link_callback,
            delink_callback=self._delink_callback,
            minimap=True,
            minimap_location=dpg.mvNodeMiniMap_Location_BottomRight,
        ) as editor:
            self._editor_id = editor

        if graph.number_of_nodes() == 0:
            return

        cycle_nodes, cycle_edges = _extract_cycle_info(cycles or [])
        visual = _build_visual_graph(graph)
        computed_positions = _compute_layout(visual)

        # Merge saved positions over computed positions
        positions = computed_positions
        if saved_positions:
            for key, pos in saved_positions.items():
                if key in positions:
                    positions[key] = pos

        # Recipe nodes (crafted items with input pins)
        for item_id in graph.nodes:
            node_data = graph.nodes[item_id]
            if not node_data.get("is_crafted"):
                continue

            node_type = classifications.get(item_id, NodeType.RAW_MATERIAL)
            pos = positions.get(item_id, [0.0, 0.0])

            ingredients = [
                (str(target), int(ed.get("required", 1)))
                for _, target, ed in graph.out_edges(item_id, data=True)
            ]

            # Look up the model object for editing back-reference
            model_recipe = recipes_by_id.get(item_id) if recipes_by_id else None

            # Derive NodeKind from model object; fall back to graph metadata
            if model_recipe is not None:
                node_kind = kind_from_recipe(model_recipe)
            else:
                raw_type = str(node_data.get("recipe_type", ""))
                node_kind = _RECIPE_TYPE_STR_TO_KIND.get(raw_type, NodeKind.MODIFIED_RECIPE)

            sprite = resolve_sprite(item_id, manual_sprites or {}, sprite_lookup or {})
            recipe_node = RecipeNode(
                item_id=item_id,
                node_type=node_type,
                kind=node_kind,
                source_file=str(node_data.get("source_file", "")),
                ingredients=ingredients,
                recipe=model_recipe,
                sprite_path=sprite,
            )
            recipe_node.create(editor, pos, self.theme, texture_cache=self.texture_cache)
            self.nodes[item_id] = recipe_node

            # Populate reverse map for attribute -> node resolution
            self._attr_to_node[recipe_node.output_attr] = (
                recipe_node,
                "__output__",
            )
            for ing_name, attr_id in recipe_node.input_attrs.items():
                self._attr_to_node[attr_id] = (recipe_node, ing_name)
            if recipe_node.hierarchy_input_attr:
                self._attr_to_node[recipe_node.hierarchy_input_attr] = (
                    recipe_node,
                    "__hierarchy__",
                )

            # Override: cycle -> red, no ingredients -> gray
            if item_id in cycle_nodes:
                dpg.bind_item_theme(recipe_node.dpg_tag, self.theme.get_cycle())
            elif not ingredients:
                dpg.bind_item_theme(recipe_node.dpg_tag, self.theme.get_unconnected())

        # Ingredient instance nodes + links (one per edge)
        for recipe_id, ing_id in graph.edges:
            instance_key = f"{recipe_id}::{ing_id}"
            ing_type = classifications.get(ing_id, NodeType.RAW_MATERIAL)
            pos = positions.get(instance_key, [0.0, 0.0])
            ing_data = graph.nodes.get(ing_id, {})

            ing_sprite = resolve_sprite(ing_id, manual_sprites or {}, sprite_lookup or {})
            instance = RecipeNode(
                item_id=ing_id,
                node_type=ing_type,
                kind=NodeKind.INGREDIENT,
                source_file=str(ing_data.get("source_file", "")),
                ingredients=[],
                sprite_path=ing_sprite,
            )
            instance.create(editor, pos, self.theme, texture_cache=self.texture_cache)
            self.nodes[instance_key] = instance

            # Populate reverse map for instance attributes
            self._attr_to_node[instance.output_attr] = (
                instance,
                "__output__",
            )
            for attr_name, attr_id in instance.input_attrs.items():
                self._attr_to_node[attr_id] = (instance, attr_name)

            # Override: cycle edge -> red instance node
            is_cycle_edge = (recipe_id, ing_id) in cycle_edges
            if is_cycle_edge:
                dpg.bind_item_theme(instance.dpg_tag, self.theme.get_cycle())

            # Wire link: instance output -> recipe input
            target_recipe = self.nodes.get(recipe_id)
            if not target_recipe or not instance.output_attr:
                continue
            input_attr = target_recipe.input_attrs.get(ing_id)
            if input_attr is None:
                continue

            link_id = int(
                dpg.add_node_link(
                    instance.output_attr,
                    input_attr,
                    parent=self._editor_id,
                )
            )
            self.links.append(
                Link(
                    source_attr=instance.output_attr,
                    target_attr=input_attr,
                    link_id=link_id,
                )
            )

            # Override: cycle edge -> red link
            if is_cycle_edge:
                dpg.bind_item_theme(link_id, self.theme.get_cycle_link())

    def get_current_positions(self) -> dict[str, list[float]]:
        """Read the current DPG position of every node.

        Returns a dict mapping node keys to [x, y] pairs. Used by the
        interactive editor to save positions before a visual rebuild and
        by the layout store for persistent storage.
        """
        positions: dict[str, list[float]] = {}
        for node_key, recipe_node in self.nodes.items():
            if recipe_node.dpg_tag and dpg.does_item_exist(recipe_node.dpg_tag):
                raw_pos = dpg.get_item_pos(recipe_node.dpg_tag)
                positions[node_key] = [float(raw_pos[0]), float(raw_pos[1])]
        return positions

    def reset_layout(self) -> None:
        """Recompute positions and move all DPG nodes to their new locations."""
        if self._graph is None or not self.nodes:
            return

        visual = _build_visual_graph(self._graph)
        positions = _compute_layout(visual)

        for node_key, recipe_node in self.nodes.items():
            pos = positions.get(node_key)
            if pos is not None and recipe_node.dpg_tag:
                dpg.set_item_pos(recipe_node.dpg_tag, [int(pos[0]), int(pos[1])])


# -- Cycle extraction ----------------------------------------------------------


def _extract_cycle_info(
    cycles: list[list[str]],
) -> tuple[set[str], set[tuple[str, str]]]:
    """Collect all node IDs and directed edges that participate in any cycle.

    For cycle [A, B, C]: nodes = {A, B, C}, edges = {(A,B), (B,C), (C,A)}.
    """
    cycle_nodes: set[str] = set()
    cycle_edges: set[tuple[str, str]] = set()
    for cycle in cycles:
        for node in cycle:
            cycle_nodes.add(node)
        for i in range(len(cycle)):
            cycle_edges.add((cycle[i], cycle[(i + 1) % len(cycle)]))
    return cycle_nodes, cycle_edges


# -- Visual graph and layout ---------------------------------------------------

# Layout tuning constants
_NODE_BOX_PADDING = 200  # approximate rendered node size added to bounding box
_CLUSTER_GAP = 120  # pixels between adjacent clusters
_LAYOUT_MARGIN = 50  # margin from the top-left corner
_MAX_ROW_WIDTH = 5000  # max pixel width before wrapping to the next row


def _build_visual_graph(graph: nx.DiGraph[str]) -> nx.DiGraph[str]:
    """Build a layout graph with per-usage ingredient instance nodes.

    Recipe (crafted) items keep their original node key. Each ingredient
    usage becomes a separate instance node keyed ``"recipe_id::ingredient_id"``.
    Edges go from instance to recipe so the spring layout pulls each
    ingredient cluster toward its recipe.
    """
    visual: nx.DiGraph[str] = nx.DiGraph()

    for item_id in graph.nodes:
        if graph.nodes[item_id].get("is_crafted"):
            visual.add_node(item_id, is_recipe=True)

    for recipe_id, ing_id in graph.edges:
        instance_key = f"{recipe_id}::{ing_id}"
        visual.add_node(instance_key, is_recipe=False)
        visual.add_edge(instance_key, recipe_id)

    return visual


def _layout_component(subgraph: nx.DiGraph[str]) -> dict[str, list[float]]:
    """Lay out a single connected component with two-layer spring physics.

    Ingredient instances are placed on the left (layer 0), recipe nodes
    on the right (layer 1). Spring physics refines positions so that
    connected nodes cluster together.

    Returns positions normalized so the minimum x and y are both zero.
    """
    node_count = subgraph.number_of_nodes()
    if node_count == 0:
        return {}

    working = subgraph.copy()
    for node in working.nodes:
        is_recipe = working.nodes[node].get("is_recipe", False)
        working.nodes[node]["subset"] = 1 if is_recipe else 0

    initial_pos = nx.multipartite_layout(working, subset_key="subset", scale=1.0)

    # Scale proportional to sqrt(node count). Each DPG node with ingredient
    # pins is roughly 180x80px, so 130*sqrt(n) gives comfortable spacing.
    scale = int(max(150, min(4000, 130 * node_count**0.5)))

    raw_positions = nx.spring_layout(
        subgraph,
        pos=initial_pos,
        seed=42,
        k=2.0 / max(1, node_count**0.4),
        iterations=25,
        scale=scale,
        center=(0.0, 0.0),
    )

    positions = {str(n): [float(p[0]), float(p[1])] for n, p in raw_positions.items()}
    if not positions:
        return {}

    # Normalize so the top-left node sits at (0, 0)
    min_x = min(p[0] for p in positions.values())
    min_y = min(p[1] for p in positions.values())
    return {n: [p[0] - min_x, p[1] - min_y] for n, p in positions.items()}


def _compute_layout(visual_graph: nx.DiGraph[str]) -> dict[str, list[float]]:
    """Compute 2D positions with connected-component clustering.

    Detects weakly connected components and lays out each independently
    with the two-layer spring algorithm. Clusters are then arranged in a
    flow grid: left-to-right, wrapping to a new row when the accumulated
    width exceeds ``_MAX_ROW_WIDTH``. Largest components are placed first.
    """
    if visual_graph.number_of_nodes() == 0:
        return {}

    # Weakly connected components, largest first
    components = sorted(
        nx.weakly_connected_components(visual_graph),
        key=len,
        reverse=True,
    )

    # Lay out each component independently and record bounding boxes
    clusters: list[tuple[float, float, dict[str, list[float]]]] = []
    for component_nodes in components:
        subgraph: nx.DiGraph[str] = visual_graph.subgraph(component_nodes).copy()  # type: ignore[assignment]
        positions = _layout_component(subgraph)
        if not positions:
            continue

        xs = [p[0] for p in positions.values()]
        ys = [p[1] for p in positions.values()]
        width = max(xs) - min(xs) + _NODE_BOX_PADDING
        height = max(ys) - min(ys) + _NODE_BOX_PADDING
        clusters.append((width, height, positions))

    # Flow grid: place clusters left-to-right, wrap on row overflow
    all_positions: dict[str, list[float]] = {}
    cursor_x = float(_LAYOUT_MARGIN)
    cursor_y = float(_LAYOUT_MARGIN)
    row_height = 0.0

    for width, height, positions in clusters:
        if cursor_x + width > _MAX_ROW_WIDTH and cursor_x > _LAYOUT_MARGIN:
            cursor_x = float(_LAYOUT_MARGIN)
            cursor_y += row_height + _CLUSTER_GAP
            row_height = 0.0

        for node, pos in positions.items():
            all_positions[node] = [pos[0] + cursor_x, pos[1] + cursor_y]

        cursor_x += width + _CLUSTER_GAP
        row_height = max(row_height, height)

    return all_positions
