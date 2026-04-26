"""Model-to-UI synchronization layer (Step M4).

Bridges the data model (models.py) and the NodeGraphQt visual editor.
Provides:
  - ``SyncGuard``: prevents recursive model <-> UI update loops
  - ``populate_graph``: creates NodeGraphQt nodes from ParsedFile(s)
  - ``connect_hierarchy``: wires Fabricator -> Tab -> Recipe connections
  - ``connect_ingredients``: wires recipe output -> ingredient input connections
  - ``UIToModelHandler``: translates NodeGraphQt signals into EditCommand objects
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from craftgraph.config import get_config

if TYPE_CHECKING:
    from NodeGraphQt import BaseNode, NodeGraph

    from craftgraph.commands import EditHistory
    from craftgraph.models import ParsedFile
    from craftgraph.qt_nodes import CraftGraphBaseNode

# Model objects are mutable dataclasses (unhashable), so we key by id().
ModelNodeMap = dict[int, "CraftGraphBaseNode"]


class SyncGuard:
    """Prevents recursive update loops between the model and UI layers.

    When the model changes, the UI must update. When the UI changes, the
    model must update. Without a guard, this creates an infinite cycle:
    model change -> UI update -> model change -> ...

    Usage::

        guard = SyncGuard()

        def on_model_changed():
            if guard.active:
                return
            with guard:
                update_ui_from_model()

        def on_ui_changed():
            if guard.active:
                return
            with guard:
                update_model_from_ui()
    """

    def __init__(self) -> None:
        self._depth: int = 0

    @property
    def active(self) -> bool:
        """True when a sync operation is already in progress."""
        return self._depth > 0

    @contextmanager
    def __call__(self) -> Generator[None]:
        """Context manager that activates the guard for a sync operation."""
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1

    def reset(self) -> None:
        """Force-reset the guard depth to zero (for testing or error recovery)."""
        self._depth = 0


# ---------------------------------------------------------------------------
# Model-to-UI: node creation
# ---------------------------------------------------------------------------

# Layout constants (defaults from config.toml [ui.layout]).
_LAYOUT_CFG = get_config().ui.layout
_Y_STEP = _LAYOUT_CFG.y_step
_X_FAB = _LAYOUT_CFG.x_fab
_X_TAB = _LAYOUT_CFG.x_tab
_X_RECIPE = _LAYOUT_CFG.x_recipe


def _node_type_for_recipe(recipe: object) -> str:
    """Return the NodeGraphQt type string for a recipe model object."""
    from craftgraph.models import AddedRecipe, AliasRecipe, CustomFood
    from craftgraph.qt_nodes import IDENTIFIER

    if isinstance(recipe, CustomFood):
        return f"{IDENTIFIER}.CustomFoodNode"
    if isinstance(recipe, AliasRecipe):
        return f"{IDENTIFIER}.AliasRecipeNode"
    if isinstance(recipe, AddedRecipe):
        return f"{IDENTIFIER}.AddedRecipeNode"
    return f"{IDENTIFIER}.ModifiedRecipeNode"


def _create_recipe_node(
    graph: NodeGraph,
    recipe: object,
    y_pos: float,
) -> tuple[CraftGraphBaseNode, float]:
    """Create a single recipe node and return (node, next_y_pos)."""
    node_type = _node_type_for_recipe(recipe)
    node = graph.create_node(
        node_type,
        name=recipe.item_id or "Recipe",  # type: ignore[attr-defined]
        pos=[_X_RECIPE, y_pos],
    )
    node.model_ref = recipe
    node.populate_from_model()
    return node, y_pos + _Y_STEP


def _create_tab_node(
    graph: NodeGraph,
    tab: object,
    y_pos: float,
) -> tuple[CraftGraphBaseNode, float]:
    """Create a single CraftingTabNode and return (node, next_y_pos)."""
    from craftgraph.qt_nodes import IDENTIFIER

    node = graph.create_node(
        f"{IDENTIFIER}.CraftingTabNode",
        name=tab.tab_id or "Tab",  # type: ignore[attr-defined]
        pos=[_X_TAB, y_pos],
    )
    node.model_ref = tab
    node.populate_from_model()
    return node, y_pos + _Y_STEP


def _create_fab_node(
    graph: NodeGraph,
    fab: object,
    y_pos: float,
) -> tuple[CraftGraphBaseNode, float]:
    """Create a FabricatorNode and return (node, next_y_pos)."""
    from craftgraph.qt_nodes import IDENTIFIER

    node = graph.create_node(
        f"{IDENTIFIER}.FabricatorNode",
        name=fab.item_id or "Fabricator",  # type: ignore[attr-defined]
        pos=[_X_FAB, y_pos],
    )
    node.model_ref = fab
    node.populate_from_model()
    return node, y_pos + _Y_STEP


def _create_size_node(
    graph: NodeGraph,
    size: object,
    y_pos: float,
) -> tuple[CraftGraphBaseNode, float]:
    """Create a CustomSizeNode and return (node, next_y_pos)."""
    from craftgraph.qt_nodes import IDENTIFIER

    node = graph.create_node(
        f"{IDENTIFIER}.CustomSizeNode",
        name=size.item_id or "Size",  # type: ignore[attr-defined]
        pos=[_X_RECIPE, y_pos],
    )
    node.model_ref = size
    node.populate_from_model()
    return node, y_pos + _Y_STEP


def _create_moved_recipe_node(
    graph: NodeGraph,
    moved: object,
    y_pos: float,
) -> tuple[CraftGraphBaseNode, float]:
    """Create a MovedRecipeNode and return (node, next_y_pos)."""
    from craftgraph.qt_nodes import IDENTIFIER

    node = graph.create_node(
        f"{IDENTIFIER}.MovedRecipeNode",
        name=moved.item_id or "Moved",  # type: ignore[attr-defined]
        pos=[_X_RECIPE, y_pos],
    )
    node.model_ref = moved
    node.populate_from_model()
    return node, y_pos + _Y_STEP


def _create_bio_fuel_node(
    graph: NodeGraph,
    fuel: object,
    y_pos: float,
) -> tuple[CraftGraphBaseNode, float]:
    """Create a CustomBioFuelNode and return (node, next_y_pos)."""
    from craftgraph.qt_nodes import IDENTIFIER

    node = graph.create_node(
        f"{IDENTIFIER}.CustomBioFuelNode",
        name=fuel.item_id or "BioFuel",  # type: ignore[attr-defined]
        pos=[_X_RECIPE, y_pos],
    )
    node.model_ref = fuel
    node.populate_from_model()
    return node, y_pos + _Y_STEP


def _create_fragment_count_node(
    graph: NodeGraph,
    frag: object,
    y_pos: float,
) -> tuple[CraftGraphBaseNode, float]:
    """Create a CustomFragmentCountNode and return (node, next_y_pos)."""
    from craftgraph.qt_nodes import IDENTIFIER

    node = graph.create_node(
        f"{IDENTIFIER}.CustomFragmentCountNode",
        name=frag.item_id or "Fragments",  # type: ignore[attr-defined]
        pos=[_X_RECIPE, y_pos],
    )
    node.model_ref = frag
    node.populate_from_model()
    return node, y_pos + _Y_STEP


def populate_graph(
    graph: NodeGraph,
    parsed_files: list[ParsedFile],
    edit_history: EditHistory | None = None,
) -> ModelNodeMap:
    """Create NodeGraphQt nodes for every entry in *parsed_files*.

    Returns a mapping from ``id(model_object)`` -> NodeGraphQt node.
    Model objects are mutable dataclasses (unhashable), so we key by
    ``id()`` for identity-based lookup.

    If *edit_history* is provided, it is injected into every created
    node via ``node.set_edit_history()`` so that auto-wired
    ``_on_field_changed`` callbacks can push undoable commands.
    """
    model_to_node: ModelNodeMap = {}
    y_pos = 0.0

    for pf in parsed_files:
        # Fabricators and their nested contents
        for fab in pf.custom_fabricators:
            fnode, y_pos = _create_fab_node(graph, fab, y_pos)
            model_to_node[id(fab)] = fnode

            for tab in fab.tabs:
                tnode, y_pos = _create_tab_node(graph, tab, y_pos)
                model_to_node[id(tab)] = tnode

            for recipe in fab.added_recipes:
                rnode, y_pos = _create_recipe_node(graph, recipe, y_pos)
                model_to_node[id(recipe)] = rnode

            for recipe in fab.alias_recipes:
                rnode, y_pos = _create_recipe_node(graph, recipe, y_pos)
                model_to_node[id(recipe)] = rnode

            for recipe in fab.custom_foods:
                rnode, y_pos = _create_recipe_node(graph, recipe, y_pos)
                model_to_node[id(recipe)] = rnode

        # Top-level tabs
        for tab in pf.crafting_tabs:
            tnode, y_pos = _create_tab_node(graph, tab, y_pos)
            model_to_node[id(tab)] = tnode

        # Top-level recipes
        for recipe in pf.modified_recipes:
            rnode, y_pos = _create_recipe_node(graph, recipe, y_pos)
            model_to_node[id(recipe)] = rnode

        for recipe in pf.added_recipes:
            rnode, y_pos = _create_recipe_node(graph, recipe, y_pos)
            model_to_node[id(recipe)] = rnode

        for recipe in pf.alias_recipes:
            rnode, y_pos = _create_recipe_node(graph, recipe, y_pos)
            model_to_node[id(recipe)] = rnode

        for recipe in pf.custom_foods:
            rnode, y_pos = _create_recipe_node(graph, recipe, y_pos)
            model_to_node[id(recipe)] = rnode

        # Custom sizes
        for size in pf.custom_sizes:
            snode, y_pos = _create_size_node(graph, size, y_pos)
            model_to_node[id(size)] = snode

        # Moved recipes
        for moved in pf.moved_recipes:
            mnode, y_pos = _create_moved_recipe_node(graph, moved, y_pos)
            model_to_node[id(moved)] = mnode

        # Custom bio fuels
        for fuel in pf.custom_bio_fuels:
            bnode, y_pos = _create_bio_fuel_node(graph, fuel, y_pos)
            model_to_node[id(fuel)] = bnode

        # Custom fragment counts
        for frag in pf.custom_fragment_counts:
            fnode, y_pos = _create_fragment_count_node(graph, frag, y_pos)
            model_to_node[id(frag)] = fnode

    # Inject edit history into all created nodes
    if edit_history is not None:
        for node in model_to_node.values():
            node.set_edit_history(edit_history)

    return model_to_node


# ---------------------------------------------------------------------------
# Model-to-UI: hierarchy-aware layout
# ---------------------------------------------------------------------------

# Layout column X positions (defaults from config.toml [ui.layout]).
_LAYOUT_X_FAB = _LAYOUT_CFG.x_fab
_LAYOUT_X_TAB = _LAYOUT_CFG.x_tab
_LAYOUT_X_RECIPE = _LAYOUT_CFG.x_recipe

# Horizontal step per nesting level (matches gap between tab and recipe columns).
# Depth-0 tabs stay at _LAYOUT_X_TAB, depth-1 child tabs shift right by this
# amount, and recipes are always one step right of their parent tab.
_LAYOUT_X_CHILD_OFFSET = _LAYOUT_CFG.layout_x_child_offset

# Vertical spacing
_LAYOUT_Y_STEP = _LAYOUT_CFG.layout_y_step
_LAYOUT_Y_GROUP_GAP = _LAYOUT_CFG.layout_y_group_gap

# Height estimation for dynamic vertical spacing
_NODE_V_PAD = 30.0  # vertical gap between adjacent nodes


def _node_step(model_id: int, model_to_node: ModelNodeMap) -> float:
    """Return the vertical advance for a node: actual height + padding.

    Queries the node's QGraphicsItem bounding rect for the real rendered
    height.  Falls back to ``_LAYOUT_Y_STEP`` when the node is not found
    or has no view geometry yet.
    """
    node = model_to_node.get(model_id)
    if node is None:
        return _LAYOUT_Y_STEP
    view = getattr(node, "view", None)
    if view is not None:
        height = view.boundingRect().height()
        if height > 0:
            return height + _NODE_V_PAD
    return _LAYOUT_Y_STEP

# Processing order for non-fabricator block types.  Each type with entries
# gets its own column, arranged left-to-right in this order.
_TOPLEVEL_COLUMN_ORDER: list[str] = [
    "crafting_tabs",
    "modified_recipes",
    "added_recipes",
    "alias_recipes",
    "custom_foods",
    "moved_recipes",
    "custom_sizes",
    "custom_bio_fuels",
    "custom_fragment_counts",
]


def _compute_tab_depths(tabs: list[object]) -> dict[str, int]:
    """Compute nesting depths for all tabs in a fabricator.

    Returns a mapping from ``tab_id`` (lowercase) to depth (0 = root tab).
    Depth is determined by walking the ``parent_tab_path`` chain: a tab
    whose parent is a depth-0 tab has depth 1, and so on.
    """
    parent_map: dict[str, str] = {}
    for tab in tabs:
        parent_path = getattr(tab, "parent_tab_path", "") or ""
        if parent_path:
            parent_id = parent_path.rsplit("/", 1)[-1].lower()
            parent_map[tab.tab_id.lower()] = parent_id  # type: ignore[attr-defined]

    depths: dict[str, int] = {}
    for tab in tabs:
        tid = tab.tab_id.lower()  # type: ignore[attr-defined]
        if tid in depths:
            continue
        depth = 0
        current = tid
        seen: set[str] = set()
        while current in parent_map and current not in seen:
            seen.add(current)
            current = parent_map[current]
            depth += 1
        depths[tid] = depth

    return depths


def _recipe_parent_depth(
    path: str,
    fab_item_id: str,
    tab_depths: dict[str, int],
) -> int:
    """Return the nesting depth of a recipe's parent tab.

    The last segment of *path* identifies the parent tab (or the
    fabricator itself).  Returns 0 when the recipe sits directly
    under the fabricator or under a root tab.
    """
    if not path:
        return 0
    last = path.rsplit("/", 1)[-1].lower()
    if last == fab_item_id.lower():
        return 0
    return tab_depths.get(last, 0)


def _layout_fab_children_dfs(
    fab: object,
    tab_depths: dict[str, int],
    model_to_node: ModelNodeMap,
    positions: dict[int, tuple[float, float]],
    y_start: float,
) -> float:
    """Lay out a fabricator's tabs and recipes in a left-to-right DFS tree.

    Children are placed to the *right* of their parent (depth-based X)
    and only advance Y when siblings or additional children are added.
    Returns the Y position after the last placed item.
    """
    fab_id = getattr(fab, "item_id", "").lower()

    # Build parent -> children maps for tabs
    tab_by_id: dict[str, object] = {}
    children_of_tab: dict[str, list[object]] = {}
    root_tabs: list[object] = []
    for tab in getattr(fab, "tabs", []):
        tid = tab.tab_id.lower()  # type: ignore[attr-defined]
        tab_by_id[tid] = tab
        parent_path = getattr(tab, "parent_tab_path", "") or ""
        if parent_path:
            parent_id = parent_path.rsplit("/", 1)[-1].lower()
            children_of_tab.setdefault(parent_id, []).append(tab)
        else:
            root_tabs.append(tab)

    # Build tab -> recipes map (recipes grouped by their parent tab)
    recipes_of_tab: dict[str, list[object]] = {}
    fab_direct_recipes: list[object] = []
    for recipe_list in (
        getattr(fab, "added_recipes", []),
        getattr(fab, "alias_recipes", []),
        getattr(fab, "custom_foods", []),
    ):
        for recipe in recipe_list:
            if id(recipe) not in model_to_node:
                continue
            path = getattr(recipe, "path", "") or ""
            if not path:
                fab_direct_recipes.append(recipe)
                continue
            last_seg = path.rsplit("/", 1)[-1].lower()
            if last_seg == fab_id:
                fab_direct_recipes.append(recipe)
            else:
                recipes_of_tab.setdefault(last_seg, []).append(recipe)

    y = y_start

    def place_tab_tree(tab: object, depth: int) -> None:
        nonlocal y
        tid = tab.tab_id.lower()  # type: ignore[attr-defined]
        if id(tab) not in model_to_node:
            return
        x = _LAYOUT_X_TAB + depth * _LAYOUT_X_CHILD_OFFSET
        positions[id(tab)] = (x, y)
        y += _node_step(id(tab), model_to_node)

        # Place recipes belonging to this tab (one depth level right)
        for recipe in recipes_of_tab.get(tid, []):
            rx = _LAYOUT_X_TAB + (depth + 1) * _LAYOUT_X_CHILD_OFFSET
            positions[id(recipe)] = (rx, y)
            y += _node_step(id(recipe), model_to_node)

        # Recurse into child tabs
        for child in children_of_tab.get(tid, []):
            place_tab_tree(child, depth + 1)

    # Place root tabs and their subtrees
    for tab in root_tabs:
        depth = tab_depths.get(tab.tab_id.lower(), 0)  # type: ignore[attr-defined]
        place_tab_tree(tab, depth)

    # Place recipes directly under the fabricator (no parent tab)
    for recipe in fab_direct_recipes:
        rx = _LAYOUT_X_TAB + _LAYOUT_X_CHILD_OFFSET
        positions[id(recipe)] = (rx, y)
        y += _node_step(id(recipe), model_to_node)

    return max(y, y_start + _node_step(id(fab), model_to_node))


def compute_hierarchy_layout(
    parsed_files: list[ParsedFile],
    model_to_node: ModelNodeMap,
) -> dict[int, tuple[float, float]]:
    """Compute hierarchy-aware node positions from the model structure.

    Returns a mapping from ``id(model_object)`` to ``(x, y)`` positions.

    Layout strategy:

    **Phase 1 -- Fabricator groups (DFS tree):**
    Fabricators at X=-400, root tabs at X=-100, child tabs shift right by
    ``_LAYOUT_X_CHILD_OFFSET`` per nesting level.  Recipes placed one step
    right of their parent tab (DFS order).

    **Phase 2 -- Column-per-block-type:**
    After fabricator groups, each remaining block type with entries gets
    its own column, arranged left-to-right in processing order
    (Tabs -> Modified -> Added -> ... -> FragmentCounts).  All columns
    start at the same Y so related types sit side by side.
    """
    positions: dict[int, tuple[float, float]] = {}
    y = 0.0

    for pf in parsed_files:
        # Phase 1: fabricator groups (tree DFS layout -- children right of parent)
        for fab in pf.custom_fabricators:
            if id(fab) not in model_to_node:
                continue

            group_start = y
            positions[id(fab)] = (_LAYOUT_X_FAB, group_start)

            tab_depths = _compute_tab_depths(fab.tabs)
            y = _layout_fab_children_dfs(
                fab,
                tab_depths,
                model_to_node,
                positions,
                group_start,
            )
            y += _LAYOUT_Y_GROUP_GAP

        # Phase 2: column-per-block-type for all non-fabricator items.
        # Each block type with entries gets its own column, arranged
        # left-to-right in processing order.  All columns start at the
        # same Y so related types sit side by side.
        section_y = y
        col_index = 0
        max_col_y = y

        for attr in _TOPLEVEL_COLUMN_ORDER:
            items = [
                item for item in getattr(pf, attr)
                if id(item) in model_to_node
            ]
            if not items:
                continue

            col_x = _LAYOUT_X_TAB + col_index * _LAYOUT_X_CHILD_OFFSET
            col_y = section_y

            for item in items:
                positions[id(item)] = (col_x, col_y)
                col_y += _node_step(id(item), model_to_node)

            max_col_y = max(max_col_y, col_y)
            col_index += 1

        y = max_col_y

    return positions


def apply_layout(
    positions: dict[int, tuple[float, float]],
    model_to_node: ModelNodeMap,
) -> None:
    """Apply computed positions to NodeGraphQt nodes.

    Calls ``node.set_pos(x, y)`` for every model object in *positions*
    that has a corresponding entry in *model_to_node*.
    """
    for model_id, (x, y) in positions.items():
        node = model_to_node.get(model_id)
        if node is not None:
            node.set_pos(x, y)


_VAR_X_OFFSET = 200.0


def place_variable_nodes(graph: NodeGraph) -> None:
    """Place variable nodes at smart positions based on their connections.

    For each variable node with connected consumers, positions it at:

    - **X:** one offset left of the leftmost consumer
    - **Y:** centroid (mean) of all consumer Y positions

    Variable nodes without connections are left at their current position.
    """
    for node in graph.all_nodes():
        if not getattr(node, "IS_VARIABLE", False):
            continue

        out_port = node.get_output("value_out")
        if out_port is None:
            continue

        connected = out_port.connected_ports()
        if not connected:
            continue

        consumer_xs: list[float] = []
        consumer_ys: list[float] = []
        for port in connected:
            cx, cy = port.node().pos()
            consumer_xs.append(cx)
            consumer_ys.append(cy)

        target_x = min(consumer_xs) - _VAR_X_OFFSET
        target_y = sum(consumer_ys) / len(consumer_ys)
        node.set_pos(target_x, target_y)


_ORPHAN_X_OFFSET = 200.0


def place_orphan_nodes(graph: NodeGraph) -> None:
    """Place orphan ingredient nodes left of their connected consumers.

    Mirrors ``place_variable_nodes``: for each orphan with connections,
    positions at X = leftmost consumer X - offset, Y = centroid of
    consumer Y positions.  Orphans without connections are left as-is.
    """
    for node in graph.all_nodes():
        if not getattr(node, "IS_ORPHAN", False):
            continue

        out_port = node.get_output("output")
        if out_port is None:
            continue

        connected = out_port.connected_ports()
        if not connected:
            continue

        consumer_xs: list[float] = []
        consumer_ys: list[float] = []
        for port in connected:
            cx, cy = port.node().pos()
            consumer_xs.append(cx)
            consumer_ys.append(cy)

        target_x = min(consumer_xs) - _ORPHAN_X_OFFSET
        target_y = sum(consumer_ys) / len(consumer_ys)
        node.set_pos(target_x, target_y)


def model_position_key(model: object) -> str:
    """Return a stable string key for a model object's position.

    Keys use the format ``"ClassName:identifier"`` so they survive
    model re-creation during re-parses.  The identifier is ``item_id``
    for most types and ``tab_id`` for ``CraftingTab``.
    """
    cls_name = type(model).__name__
    identifier = getattr(model, "item_id", None) or getattr(model, "tab_id", "")
    return f"{cls_name}:{identifier}"


def overlay_user_positions(
    positions: dict[int, tuple[float, float]],
    user_positions: dict[str, tuple[float, float]],
    model_to_node: ModelNodeMap,
) -> None:
    """Replace computed positions with user-dragged positions where available.

    Mutates *positions* in-place: for each node whose
    ``model_position_key`` exists in *user_positions*, the computed
    position is replaced with the user's saved position.
    """
    for model_id, node in model_to_node.items():
        ref = node.model_ref
        if ref is None:
            continue
        key = model_position_key(ref)
        if key in user_positions:
            positions[model_id] = user_positions[key]


# ---------------------------------------------------------------------------
# Model-to-UI: child count labels
# ---------------------------------------------------------------------------


def update_child_count_labels(model_to_node: ModelNodeMap) -> None:
    """Update hierarchy output port labels with connection counts.

    Fabricator nodes (with ``SPLIT_OUTPUTS``) have typed output ports
    (``tabs_out``, ``added_out``, etc.).  CraftingTab nodes have a
    single ``children`` output port.  This function sets the displayed
    label to ``"port_name (N)"`` where *N* is the number of currently
    connected ports, giving users a quick visual indicator of how many
    tabs/recipes are nested under each container node.

    Accesses NodeGraphQt internals (``node.view.get_output_text_item``)
    because there is no public API for changing port labels after creation.
    """
    from craftgraph.qt_nodes import CraftingTabNode, FabricatorNode

    for node in model_to_node.values():
        if not isinstance(node, (FabricatorNode, CraftingTabNode)):
            continue

        if isinstance(node, FabricatorNode) and node.SPLIT_OUTPUTS:
            # Update each typed output port label
            for port_name in ("tabs_out", "added_out", "alias_out", "foods_out", "moved_out"):
                port = node.get_output(port_name)
                if port is None:
                    continue
                count = len(port.connected_ports())
                label = f"{port_name} ({count})" if count > 0 else port_name
                text_item = node.view.get_output_text_item(port.view)
                if text_item is not None:
                    text_item.setPlainText(label)
        else:
            # CraftingTabNode or non-split fabricator
            port = node.get_output("children")
            if port is None:
                continue
            count = len(port.connected_ports())
            label = f"children ({count})" if count > 0 else "children"
            text_item = node.view.get_output_text_item(port.view)
            if text_item is not None:
                text_item.setPlainText(label)


# ---------------------------------------------------------------------------
# Model-to-UI: cycle edge highlighting
# ---------------------------------------------------------------------------

# Red color for cycle edges (RGBA)
_CYCLE_COLOR = (220, 60, 60, 255)
# Default pipe color (matches NodeGraphQt PipeEnum.COLOR)
_DEFAULT_PIPE_COLOR = (175, 95, 30, 255)


def highlight_cycle_edges(
    graph: NodeGraph,
    parsed_files: list[ParsedFile],
    model_to_node: ModelNodeMap,
) -> int:
    """Color ingredient pipes that participate in cycles red.

    Builds a NetworkX ingredient graph, runs ``find_cycles()``, and
    sets matching pipes to red.  Non-cycle pipes are reset to the
    default color.  Returns the number of cycles found.
    """
    from craftgraph.graph import build_graph, find_cycles

    nx_graph = build_graph(parsed_files)
    cycles = find_cycles(nx_graph)

    cycle_edges: set[tuple[str, str]] = set()
    for cycle in cycles:
        for i in range(len(cycle)):
            cycle_edges.add((cycle[i], cycle[(i + 1) % len(cycle)]))

    # Build reverse lookup: item_id -> node
    item_id_to_node: dict[str, object] = {}
    for node in model_to_node.values():
        ref = node.model_ref
        item_id = getattr(ref, "item_id", None)
        if item_id:
            item_id_to_node[item_id.lower()] = node

    viewer = graph.viewer()
    for pipe in viewer.all_pipes():
        # Identify the nodes at each end of this pipe
        out_node_item = pipe.output_port.node
        in_node_item = pipe.input_port.node

        out_node = graph.get_node_by_id(out_node_item.id)
        in_node = graph.get_node_by_id(in_node_item.id)
        if out_node is None or in_node is None:
            continue

        # Only style ingredient connections (not hierarchy)
        port_name = pipe.input_port.name
        if not port_name.startswith("ingredient_"):
            continue

        out_id = getattr(getattr(out_node, "model_ref", None), "item_id", None)
        in_id = getattr(getattr(in_node, "model_ref", None), "item_id", None)

        if out_id and in_id and (in_id, out_id) in cycle_edges:
            pipe.color = _CYCLE_COLOR
            pipe.set_pipe_styling(color=_CYCLE_COLOR, width=3)
        else:
            pipe.color = _DEFAULT_PIPE_COLOR
            pipe.set_pipe_styling(color=_DEFAULT_PIPE_COLOR, width=2)

    return len(cycles)


# ---------------------------------------------------------------------------
# Model-to-UI: per-node issue overlays (warning triangles)
# ---------------------------------------------------------------------------


def _collect_per_recipe_issues(
    parsed_files: list[ParsedFile],
    known_ids: frozenset[str],
) -> dict[int, list[str]]:
    """Return ``id(model_obj) -> list[issue_str]`` for unknown refs.

    Mirrors the model-level checks in ``validate_parsed_files`` but keys
    issues by the offending model object's ``id()`` so callers can map
    issues back to specific UI nodes.
    """
    from craftgraph.models import ModifiedRecipe

    by_model: dict[int, list[str]] = {}

    for pf in parsed_files:
        defined_ids: set[str] = set()
        all_recipes: list[ModifiedRecipe] = []
        for r in pf.modified_recipes:
            defined_ids.add(r.item_id.lower())
            all_recipes.append(r)
        for r in pf.added_recipes:
            defined_ids.add(r.item_id.lower())
            all_recipes.append(r)
        for r in pf.alias_recipes:
            defined_ids.add(r.item_id.lower())
            all_recipes.append(r)
        for r in pf.custom_foods:
            defined_ids.add(r.item_id.lower())
            all_recipes.append(r)

        for fab in pf.custom_fabricators:
            for r in fab.added_recipes:
                defined_ids.add(r.item_id.lower())
                all_recipes.append(r)
            for r in fab.alias_recipes:
                defined_ids.add(r.item_id.lower())
                all_recipes.append(r)
            for r in fab.custom_foods:
                defined_ids.add(r.item_id.lower())
                all_recipes.append(r)

        all_known = known_ids | defined_ids

        for recipe in all_recipes:
            for ing in recipe.ingredients:
                if ing.item_id.lower() not in all_known:
                    by_model.setdefault(id(recipe), []).append(
                        f"Unknown ingredient '{ing.item_id}'"
                    )

        for fab in pf.custom_fabricators:
            tab_ids = {t.tab_id.lower() for t in fab.tabs}

            for tab in fab.tabs:
                if not tab.parent_tab_path:
                    continue
                last_seg = tab.parent_tab_path.rsplit("/", 1)[-1].lower()
                if last_seg != fab.item_id.lower() and last_seg not in tab_ids:
                    by_model.setdefault(id(tab), []).append(
                        f"Parent path '{tab.parent_tab_path}' references missing tab"
                    )

            for recipe_list in (fab.added_recipes, fab.alias_recipes, fab.custom_foods):
                for recipe in recipe_list:
                    path = getattr(recipe, "path", "") or ""
                    if not path:
                        continue
                    last_seg = path.rsplit("/", 1)[-1].lower()
                    if last_seg != fab.item_id.lower() and last_seg not in tab_ids:
                        by_model.setdefault(id(recipe), []).append(
                            f"Path '{path}' references missing tab"
                        )

    return by_model


def update_node_issue_overlays(
    graph: NodeGraph,
    parsed_files: list[ParsedFile],
    model_to_node: ModelNodeMap,
    known_ids: frozenset[str],
) -> tuple[int, int]:
    """Apply warning-triangle overlays on nodes with detected issues.

    Cycle members get a red error overlay; nodes with broken references or
    unknown ingredients get a yellow warning overlay.  Returns
    ``(error_count, warning_count)``.
    """
    from craftgraph.graph import build_graph, find_cycles

    nx_graph = build_graph(parsed_files)
    cycles = find_cycles(nx_graph)
    cycle_ids: set[str] = set()
    cycle_paths: dict[str, list[str]] = {}
    for cycle in cycles:
        path_str = " -> ".join([*cycle, cycle[0]])
        for item_id in cycle:
            key = item_id.lower()
            cycle_ids.add(key)
            cycle_paths.setdefault(key, []).append(path_str)

    issues_by_model = _collect_per_recipe_issues(parsed_files, known_ids)

    error_count = 0
    warning_count = 0

    for node in model_to_node.values():
        ref = node.model_ref
        item_id = getattr(ref, "item_id", None) or getattr(ref, "tab_id", None)
        item_key = item_id.lower() if isinstance(item_id, str) else None

        node_issues = list(issues_by_model.get(id(ref), []))
        in_cycle = item_key is not None and item_key in cycle_ids
        node_cycle_paths = cycle_paths.get(item_key or "", []) if in_cycle else []

        # Stash for the hover-tooltip composer.
        node._issue_messages = list(node_issues)
        node._cycle_paths = list(node_cycle_paths)

        if in_cycle:
            tooltip_lines = ["In dependency cycle:", *node_cycle_paths]
            if node_issues:
                tooltip_lines.append("")
                tooltip_lines.extend(node_issues)
            node.set_node_warning("error", "\n".join(tooltip_lines))
            error_count += 1
        elif node_issues:
            node.set_node_warning("warning", "\n".join(node_issues))
            warning_count += 1
        else:
            node.clear_node_warning()

    return error_count, warning_count


# ---------------------------------------------------------------------------
# Model-to-UI: connection wiring
# ---------------------------------------------------------------------------


def _get_fab_output_for_child(
    fab_node: CraftGraphBaseNode,
    child_node: CraftGraphBaseNode,
) -> str:
    """Return the correct output port name on a fabricator for a given child."""
    if not fab_node.SPLIT_OUTPUTS:
        return "children"

    from craftgraph.qt_nodes import (
        AddedRecipeNode,
        AliasRecipeNode,
        CraftingTabNode,
        CustomFoodNode,
        MovedRecipeNode,
    )

    if isinstance(child_node, CraftingTabNode):
        return "tabs_out"
    if isinstance(child_node, CustomFoodNode):
        return "foods_out"
    if isinstance(child_node, AliasRecipeNode):
        return "alias_out"
    if isinstance(child_node, AddedRecipeNode):
        return "added_out"
    if isinstance(child_node, MovedRecipeNode):
        return "moved_out"
    return "added_out"


def connect_hierarchy(
    graph: NodeGraph,
    parsed_files: list[ParsedFile],
    model_to_node: ModelNodeMap,
) -> int:
    """Wire hierarchy connections respecting ParentTabPath and recipe Path.

    Tabs connect to their parent tab (or the fabricator if top-level).
    Recipes connect to the tab specified by their ``path`` field, or to
    the fabricator if no path is set.

    Returns the number of connections made.
    """
    count = 0
    for pf in parsed_files:
        for fab in pf.custom_fabricators:
            fab_node = model_to_node.get(id(fab))
            if fab_node is None:
                continue

            # Build tab_id -> node lookup for this fabricator
            tab_id_to_node: dict[str, CraftGraphBaseNode] = {}
            for tab in fab.tabs:
                node = model_to_node.get(id(tab))
                if node is not None:
                    tab_id_to_node[tab.tab_id.lower()] = node

            # Connect tabs to their parent (tab or fabricator)
            for tab in fab.tabs:
                tab_node = model_to_node.get(id(tab))
                if tab_node is None:
                    continue
                tab_in = tab_node.get_input("parent")
                if tab_in is None:
                    continue

                parent_out = _resolve_parent_output(
                    tab.parent_tab_path,
                    fab.item_id,
                    fab_node,
                    tab_node,
                    tab_id_to_node,
                )
                parent_out.connect_to(tab_in)
                count += 1

            # Connect recipes to their tab (or fabricator)
            for recipe_list in (fab.added_recipes, fab.alias_recipes, fab.custom_foods):
                for recipe in recipe_list:
                    recipe_node = model_to_node.get(id(recipe))
                    if recipe_node is None:
                        continue
                    hier_in = recipe_node.get_input("hierarchy")
                    if hier_in is None:
                        continue

                    path = getattr(recipe, "path", "") or ""
                    parent_out = _resolve_parent_output(
                        path,
                        fab.item_id,
                        fab_node,
                        recipe_node,
                        tab_id_to_node,
                    )
                    parent_out.connect_to(hier_in)
                    count += 1

    return count


def _resolve_parent_output(
    path: str,
    fab_item_id: str,
    fab_node: CraftGraphBaseNode,
    child_node: CraftGraphBaseNode,
    tab_id_to_node: dict[str, CraftGraphBaseNode],
) -> object:
    """Find the correct parent output port for a given path.

    The last segment of *path* determines the parent.  If it matches
    a tab_id, that tab's ``children`` output is returned.  Otherwise
    the fabricator's typed output port is used (via
    ``_get_fab_output_for_child``).
    """
    if not path:
        port_name = _get_fab_output_for_child(fab_node, child_node)
        return fab_node.get_output(port_name)

    last_segment = path.rsplit("/", 1)[-1]

    # If the last segment is the fabricator itself, connect to fabricator
    if last_segment.lower() == fab_item_id.lower():
        port_name = _get_fab_output_for_child(fab_node, child_node)
        return fab_node.get_output(port_name)

    # Look up the parent tab
    parent_node = tab_id_to_node.get(last_segment.lower())
    if parent_node is not None:
        parent_children = parent_node.get_output("children")
        if parent_children is not None:
            return parent_children

    # Fallback to fabricator
    port_name = _get_fab_output_for_child(fab_node, child_node)
    return fab_node.get_output(port_name)


@dataclass
class ConnectResult:
    """Result of ``connect_ingredients()``.

    Attributes:
        count: Total connections made (recipe-to-recipe + orphan-to-recipe).
        orphan_nodes: Mapping of lowercase item_id to the created
            OrphanIngredientNode for raw materials (no recipe on canvas).
    """

    count: int = 0
    orphan_nodes: dict[str, CraftGraphBaseNode] = field(default_factory=dict)


def connect_ingredients(
    graph: NodeGraph,
    parsed_files: list[ParsedFile],
    model_to_node: ModelNodeMap,
) -> ConnectResult:
    """Wire recipe output -> ingredient input connections.

    **Phase 1 -- Recipe-to-recipe:** If an ingredient ItemID matches another
    recipe node on the canvas, a direct link is created.

    **Phase 2 -- Orphan creation:** Remaining unmatched ingredients get an
    ``OrphanIngredientNode`` (one per unique ItemID, case-insensitive).
    The orphan's ``output`` port connects to every consuming recipe slot.
    """
    from craftgraph.qt_nodes import IDENTIFIER

    # Build item_id -> node lookup from recipe nodes (those with ingredients)
    item_id_to_node: dict[str, CraftGraphBaseNode] = {}
    for node in model_to_node.values():
        ref = node.model_ref
        item_id = getattr(ref, "item_id", None)
        if item_id and hasattr(ref, "ingredients"):
            item_id_to_node[item_id.lower()] = node

    result = ConnectResult()

    # Collect unmatched ingredients: key -> list of consuming nodes
    unmatched: dict[str, list[tuple[str, CraftGraphBaseNode]]] = {}

    # Phase 1: recipe-to-recipe connections
    for node in model_to_node.values():
        ref = node.model_ref
        ingredients = getattr(ref, "ingredients", None)
        if not ingredients:
            continue

        for ing in ingredients:
            key = ing.item_id.lower()
            source_node = item_id_to_node.get(key)

            if source_node is not None:
                source_out = source_node.get_output("output")
                if source_out is None:
                    continue
                ing_ports = [
                    p
                    for p in node.input_ports()
                    if p.name().startswith("ingredient_")
                    and not p.connected_ports()
                ]
                if not ing_ports:
                    continue
                source_out.connect_to(ing_ports[0])
                result.count += 1
            else:
                # Track for orphan creation in phase 2
                unmatched.setdefault(key, []).append((ing.item_id, node))

    # Phase 2: create OrphanIngredientNodes for unmatched ingredients
    for key, consumers in unmatched.items():
        # Use the original-case item_id from the first occurrence
        original_id = consumers[0][0]

        orphan = graph.create_node(
            f"{IDENTIFIER}.OrphanIngredientNode",
            name=original_id,
        )
        orphan.set_property("item_id", original_id)
        result.orphan_nodes[key] = orphan

        orphan_out = orphan.get_output("output")
        if orphan_out is None:
            continue

        for _id, consumer_node in consumers:
            ing_ports = [
                p
                for p in consumer_node.input_ports()
                if p.name().startswith("ingredient_")
                and not p.connected_ports()
            ]
            if not ing_ports:
                continue
            orphan_out.connect_to(ing_ports[0])
            result.count += 1

    return result


# ---------------------------------------------------------------------------
# Pre-save validation
# ---------------------------------------------------------------------------


def validate_parsed_files(
    parsed_files: list[ParsedFile],
    known_ids: frozenset[str],
) -> list[str]:
    """Scan parsed files for broken references before saving.

    Returns a list of human-readable issue strings (empty if all valid).
    Checks:
    - Ingredient IDs not in *known_ids*
    - ``parent_tab_path`` referencing a non-existent tab or fabricator
    - Recipe ``path`` pointing to a non-existent tab
    """
    from craftgraph.models import (
        AddedRecipe,
        CustomFabricator,
        ModifiedRecipe,
    )

    issues: list[str] = []

    for pf in parsed_files:
        # Collect all item_ids defined in this set of files (recipes define IDs)
        defined_ids: set[str] = set()
        all_recipes: list[ModifiedRecipe] = []
        for r in pf.modified_recipes:
            defined_ids.add(r.item_id.lower())
            all_recipes.append(r)
        for r in pf.added_recipes:
            defined_ids.add(r.item_id.lower())
            all_recipes.append(r)
        for r in pf.alias_recipes:
            defined_ids.add(r.item_id.lower())
            all_recipes.append(r)
        for r in pf.custom_foods:
            defined_ids.add(r.item_id.lower())
            all_recipes.append(r)

        for fab in pf.custom_fabricators:
            # Collect all recipes nested in fabricators too
            for r in fab.added_recipes:
                defined_ids.add(r.item_id.lower())
                all_recipes.append(r)
            for r in fab.alias_recipes:
                defined_ids.add(r.item_id.lower())
                all_recipes.append(r)
            for r in fab.custom_foods:
                defined_ids.add(r.item_id.lower())
                all_recipes.append(r)

        all_known = known_ids | defined_ids

        # Check ingredient IDs
        for recipe in all_recipes:
            for ing in recipe.ingredients:
                if ing.item_id.lower() not in all_known:
                    issues.append(
                        f"Unknown ingredient '{ing.item_id}' in recipe "
                        f"'{recipe.item_id}' ({pf.source_path.name})"
                    )

        # Check tab parent_tab_path and recipe paths within fabricators
        for fab in pf.custom_fabricators:
            tab_ids = {t.tab_id.lower() for t in fab.tabs}

            for tab in fab.tabs:
                if not tab.parent_tab_path:
                    continue
                last_seg = tab.parent_tab_path.rsplit("/", 1)[-1]
                if (
                    last_seg.lower() != fab.item_id.lower()
                    and last_seg.lower() not in tab_ids
                ):
                    issues.append(
                        f"Tab '{tab.tab_id}' references missing parent "
                        f"'{tab.parent_tab_path}' ({pf.source_path.name})"
                    )

            for recipe_list in (fab.added_recipes, fab.alias_recipes, fab.custom_foods):
                for recipe in recipe_list:
                    path = getattr(recipe, "path", "") or ""
                    if not path:
                        continue
                    last_seg = path.rsplit("/", 1)[-1]
                    if (
                        last_seg.lower() != fab.item_id.lower()
                        and last_seg.lower() not in tab_ids
                    ):
                        issues.append(
                            f"Recipe '{recipe.item_id}' path references "
                            f"missing tab '{last_seg}' ({pf.source_path.name})"
                        )

    return issues


# ---------------------------------------------------------------------------
# UI-to-Model: event handler
# ---------------------------------------------------------------------------


class UIToModelHandler:
    """Translates NodeGraphQt UI events into EditCommand objects.

    Connects to ``NodeGraph`` signals and creates/executes commands through
    an ``EditHistory``, enabling undo/redo for all GUI edits.

    Signal -> Command mapping:

    - ``property_changed`` -> ``ChangeRecipeFieldCommand`` or
      ``ChangeNonRecipeFieldCommand``
    - ``port_connected`` (ingredient) -> ``AddIngredientCommand``
    - ``port_disconnected`` (ingredient) -> ``RemoveIngredientCommand``
    - ``port_connected`` (hierarchy) -> ``NestTabInFabricatorCommand`` or
      ``NestRecipeInFabricatorCommand``
    - ``port_disconnected`` (hierarchy) -> ``UnnestTabFromFabricatorCommand``
      or ``UnnestRecipeFromFabricatorCommand``
    """

    def __init__(
        self,
        graph: NodeGraph,
        history: EditHistory,
        guard: SyncGuard,
        parsed_files: list[ParsedFile],
        model_to_node: ModelNodeMap | None = None,
        on_cycle_rejected: "Callable[[str, str, list[str]], None] | None" = None,
        on_reassignment_warning: "Callable[[str, str], None] | None" = None,
    ) -> None:
        self._graph = graph
        self._history = history
        self._guard = guard
        self._parsed_files = parsed_files
        self._on_cycle_rejected = on_cycle_rejected
        self._on_reassignment_warning = on_reassignment_warning
        self.warn_before_cycles: bool = True
        # Reverse map: NodeGraphQt node ID -> model object, used to look
        # up models after nodes have been deleted from the graph.
        self._node_id_to_model: dict[str, object] = {}
        if model_to_node is not None:
            for model_id, node in model_to_node.items():
                self._node_id_to_model[node.id] = node.model_ref
        self._connect_signals()

    def register_node(self, node: BaseNode) -> None:
        """Track a node's ID -> model mapping for deletion handling."""
        if node.model_ref is not None:
            self._node_id_to_model[node.id] = node.model_ref

    def _connect_signals(self) -> None:
        self._graph.property_changed.connect(self._on_property_changed)
        self._graph.port_connected.connect(self._on_port_connected)
        self._graph.port_disconnected.connect(self._on_port_disconnected)
        self._graph.nodes_deleted.connect(self._on_nodes_deleted)

    def disconnect(self) -> None:
        """Remove all signal connections (call before replacing the handler)."""
        self._graph.property_changed.disconnect(self._on_property_changed)
        self._graph.port_connected.disconnect(self._on_port_connected)
        self._graph.port_disconnected.disconnect(self._on_port_disconnected)
        self._graph.nodes_deleted.disconnect(self._on_nodes_deleted)

    # -- Signal handlers ------------------------------------------------------

    def _on_property_changed(
        self,
        node: BaseNode,
        prop_name: str,
        prop_value: object,
    ) -> None:
        if self._guard.active:
            return

        # Variable node value change: propagate to all connected consumers
        if getattr(node, "IS_VARIABLE", False) and prop_name == "value":
            self._handle_variable_value_changed(node, prop_value)
            return

        # Delegate to the node's auto-wired handler (Phase A).
        if hasattr(node, "_on_field_changed"):
            node._on_field_changed(prop_name, prop_value)

    def _on_port_connected(self, in_port: object, out_port: object) -> None:
        if self._guard.active:
            return

        port_name = in_port.name()  # type: ignore[attr-defined]

        if port_name.startswith("ingredient_"):
            self._handle_ingredient_connected(in_port, out_port)
        elif port_name in ("hierarchy", "parent"):
            self._handle_hierarchy_connected(in_port, out_port)
        elif port_name == "sprite_in":
            self._handle_sprite_connected(in_port, out_port)
        elif port_name.startswith("field_"):
            self._handle_variable_connected(in_port, out_port)

    def _on_port_disconnected(self, in_port: object, out_port: object) -> None:
        if self._guard.active:
            return

        port_name = in_port.name()  # type: ignore[attr-defined]

        if port_name.startswith("ingredient_"):
            self._handle_ingredient_disconnected(in_port, out_port)
        elif port_name in ("hierarchy", "parent"):
            self._handle_hierarchy_disconnected(in_port, out_port)
        elif port_name == "sprite_in":
            self._handle_sprite_disconnected(in_port)
        elif port_name.startswith("field_"):
            self._handle_variable_disconnected(in_port, out_port)

    def _on_nodes_deleted(self, node_ids: list[str]) -> None:
        """Remove model objects for deleted nodes from their ParsedFiles."""
        if self._guard.active:
            return

        for node_id in node_ids:
            model = self._node_id_to_model.pop(node_id, None)
            if model is None:
                continue
            self._remove_model_from_parsed_files(model)

        if self._history.on_change is not None:
            self._history.on_change()

    def _remove_model_from_parsed_files(self, model: object) -> None:
        """Remove a model object from whichever ParsedFile list contains it."""
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
        )

        for pf in self._parsed_files:
            # Check top-level lists
            for attr, cls in [
                ("modified_recipes", ModifiedRecipe),
                ("added_recipes", AddedRecipe),
                ("alias_recipes", AliasRecipe),
                ("custom_foods", CustomFood),
                ("crafting_tabs", CraftingTab),
                ("custom_sizes", CustomSize),
                ("moved_recipes", MovedRecipe),
                ("custom_bio_fuels", CustomBioFuel),
                ("custom_fragment_counts", CustomFragmentCount),
            ]:
                entries = getattr(pf, attr)
                if model in entries:
                    entries.remove(model)
                    return

            # Check inside fabricators
            for fab in pf.custom_fabricators:
                if fab is model:
                    pf.custom_fabricators.remove(fab)
                    return
                for attr in ("tabs", "added_recipes", "alias_recipes", "moved_recipes", "custom_foods"):
                    entries = getattr(fab, attr)
                    if model in entries:
                        entries.remove(model)
                        return

    # -- Cycle detection ------------------------------------------------------

    def _build_ingredient_graph(self) -> "nx.DiGraph[str]":
        """Build a NetworkX DiGraph of ingredient edges from the current model.

        Nodes are item IDs. An edge ``(A, B)`` means recipe A requires
        ingredient B. Only considers recipes with ingredients (hierarchy
        connections are excluded).
        """
        import networkx as nx

        g: nx.DiGraph[str] = nx.DiGraph()
        for pf in self._parsed_files:
            for recipe in pf.all_recipes:
                for ing in recipe.ingredients:
                    g.add_edge(recipe.item_id, ing.item_id)
            for fab in pf.custom_fabricators:
                for recipe_list in (fab.added_recipes, fab.alias_recipes, fab.custom_foods):
                    for recipe in recipe_list:
                        for ing in recipe.ingredients:
                            g.add_edge(recipe.item_id, ing.item_id)
        return g

    def find_cycle_path(self, consumer_id: str, ingredient_id: str) -> list[str] | None:
        """Return the cycle path if adding an edge would create a cycle, else None.

        The returned list is the node sequence forming the cycle,
        e.g. ``["A", "B", "C", "A"]``.
        """
        import networkx as nx

        test_graph = self._build_ingredient_graph()
        test_graph.add_edge(consumer_id, ingredient_id)
        try:
            edges = nx.find_cycle(test_graph)
        except nx.NetworkXNoCycle:
            return None
        # edges is a list of (u, v) tuples; build the node path
        path = [e[0] for e in edges]
        path.append(edges[-1][1])
        return path

    def would_create_cycle(self, consumer_id: str, ingredient_id: str) -> bool:
        """Test whether adding an ingredient edge would create a cycle."""
        return self.find_cycle_path(consumer_id, ingredient_id) is not None

    # -- Ingredient connections -----------------------------------------------

    def _handle_ingredient_connected(
        self,
        in_port: object,
        out_port: object,
    ) -> None:
        consumer_model = in_port.node().model_ref  # type: ignore[attr-defined]
        source_model = out_port.node().model_ref  # type: ignore[attr-defined]

        if consumer_model is None or source_model is None:
            return

        source_id = getattr(source_model, "item_id", None)
        consumer_id = getattr(consumer_model, "item_id", None)
        if not source_id or not consumer_id:
            return

        # Pre-link cycle check: reject connections that would create cycles
        if self.warn_before_cycles:
            cycle_path = self.find_cycle_path(consumer_id, source_id)
            if cycle_path is not None:
                with self._guard():
                    in_port.disconnect_from(out_port)  # type: ignore[attr-defined]
                if self._on_cycle_rejected is not None:
                    self._on_cycle_rejected(consumer_id, source_id, cycle_path)
                return

        from craftgraph.commands import AddIngredientCommand
        from craftgraph.models import Ingredient

        ingredient = Ingredient(item_id=source_id, required=1)
        cmd = AddIngredientCommand(recipe=consumer_model, ingredient=ingredient)

        with self._guard():
            self._history.execute(cmd)

    def _handle_ingredient_disconnected(
        self,
        in_port: object,
        out_port: object,
    ) -> None:
        consumer_model = in_port.node().model_ref  # type: ignore[attr-defined]
        source_model = out_port.node().model_ref  # type: ignore[attr-defined]

        if consumer_model is None or source_model is None:
            return

        # Extract port index from "ingredient_N"
        port_name = in_port.name()  # type: ignore[attr-defined]
        try:
            port_idx = int(port_name.split("_")[1])
        except IndexError, ValueError:
            return

        if port_idx >= len(consumer_model.ingredients):
            return

        from craftgraph.commands import RemoveIngredientCommand

        cmd = RemoveIngredientCommand(recipe=consumer_model, index=port_idx)

        with self._guard():
            self._history.execute(cmd)

    # -- Hierarchy connections ------------------------------------------------

    def _handle_hierarchy_connected(
        self,
        in_port: object,
        out_port: object,
    ) -> None:
        child_model = in_port.node().model_ref  # type: ignore[attr-defined]
        parent_model = out_port.node().model_ref  # type: ignore[attr-defined]

        if child_model is None or parent_model is None:
            return

        from craftgraph.models import AddedRecipe, CraftingTab, CustomFabricator

        # Tab-to-tab connection (parent is a CraftingTab)
        if isinstance(parent_model, CraftingTab) and isinstance(child_model, CraftingTab):
            self._handle_tab_to_tab_connected(child_model, parent_model, in_port, out_port)
            return

        if not isinstance(parent_model, CustomFabricator):
            return

        pf = self._find_parsed_file_for(child_model)
        if pf is None:
            return

        from craftgraph.commands import NestRecipeInFabricatorCommand, NestTabInFabricatorCommand

        if isinstance(child_model, CraftingTab):
            cmd = NestTabInFabricatorCommand(
                parsed_file=pf,
                fabricator=parent_model,
                tab=child_model,
            )
        elif isinstance(child_model, AddedRecipe):
            if (
                child_model.path
                and self._on_reassignment_warning is not None
            ):
                self._on_reassignment_warning(
                    child_model.item_id, child_model.path
                )
            cmd = NestRecipeInFabricatorCommand(
                parsed_file=pf,
                fabricator=parent_model,
                recipe=child_model,
                path=parent_model.item_id,
            )
        else:
            return

        with self._guard():
            self._history.execute(cmd)

    def _handle_tab_to_tab_connected(
        self,
        child: "CraftingTab",
        parent: "CraftingTab",
        in_port: object,
        out_port: object,
    ) -> None:
        """Handle connecting a tab under another tab's children port."""
        from craftgraph.models import CraftingTab

        if self.warn_before_cycles and self._would_create_tab_cycle(child, parent):
            cycle_path = [child.tab_id, parent.tab_id, child.tab_id]
            if self._on_cycle_rejected is not None:
                self._on_cycle_rejected(child.tab_id, parent.tab_id, cycle_path)
            with self._guard():
                out_port.disconnect_from(in_port)  # type: ignore[attr-defined]
            return

        with self._guard():
            child.parent_tab_path = parent.tab_id

    def _would_create_tab_cycle(
        self,
        child: "CraftingTab",
        proposed_parent: "CraftingTab",
    ) -> bool:
        """Check if setting child's parent to proposed_parent creates a cycle."""
        from craftgraph.models import CraftingTab

        # Build a tab_id -> CraftingTab lookup from all known tabs.
        # Include both fabricator-nested tabs AND top-level crafting_tabs,
        # since auto-disconnect may have moved a tab out of a fabricator
        # before this check runs.
        tab_lookup: dict[str, CraftingTab] = {}
        for pf in self._parsed_files:
            for tab in pf.crafting_tabs:
                tab_lookup[tab.tab_id.lower()] = tab
            for fab in pf.custom_fabricators:
                for tab in fab.tabs:
                    tab_lookup[tab.tab_id.lower()] = tab
        # Ensure both participants are in the lookup
        tab_lookup[child.tab_id.lower()] = child
        tab_lookup[proposed_parent.tab_id.lower()] = proposed_parent

        # Walk the parent chain from proposed_parent upward.
        # If we reach the child, there's a cycle.
        visited: set[str] = set()
        current_tab_id = proposed_parent.tab_id

        while current_tab_id:
            if current_tab_id.lower() == child.tab_id.lower():
                return True
            if current_tab_id.lower() in visited:
                break
            visited.add(current_tab_id.lower())
            current_tab = tab_lookup.get(current_tab_id.lower())
            if current_tab is None:
                break
            parent_path = current_tab.parent_tab_path
            if not parent_path:
                break
            last_segment = parent_path.rsplit("/", 1)[-1]
            if last_segment.lower() not in tab_lookup:
                break
            current_tab_id = last_segment

        return False

    def _handle_hierarchy_disconnected(
        self,
        in_port: object,
        out_port: object,
    ) -> None:
        child_model = in_port.node().model_ref  # type: ignore[attr-defined]
        parent_model = out_port.node().model_ref  # type: ignore[attr-defined]

        if child_model is None or parent_model is None:
            return

        from craftgraph.models import AddedRecipe, CraftingTab, CustomFabricator

        if not isinstance(parent_model, CustomFabricator):
            return

        # Child is nested inside the fabricator, so look for the fab's file
        pf = self._find_parsed_file_for(parent_model)
        if pf is None:
            return

        from craftgraph.commands import (
            UnnestRecipeFromFabricatorCommand,
            UnnestTabFromFabricatorCommand,
        )

        if isinstance(child_model, CraftingTab) and child_model in parent_model.tabs:
            cmd = UnnestTabFromFabricatorCommand(
                parsed_file=pf,
                fabricator=parent_model,
                tab=child_model,
            )
        elif isinstance(child_model, AddedRecipe):
            cmd = UnnestRecipeFromFabricatorCommand(
                parsed_file=pf,
                fabricator=parent_model,
                recipe=child_model,
            )
        else:
            return

        with self._guard():
            self._history.execute(cmd)

    # -- Sprite connections ---------------------------------------------------

    @staticmethod
    def _handle_sprite_connected(
        in_port: object,
        out_port: object,
    ) -> None:
        """Apply the SpriteNode's file_path as a sprite on the target node."""
        from pathlib import Path

        target = in_port.node()  # type: ignore[attr-defined]
        source = out_port.node()  # type: ignore[attr-defined]
        file_path = source.get_property("file_path")  # type: ignore[attr-defined]
        if file_path:
            path = Path(file_path)
            target.set_sprite(path)  # type: ignore[attr-defined]
            # Also set the sprite_item_id model field when available
            if target.get_widget("sprite_item_id") is not None:  # type: ignore[attr-defined]
                target.set_property("sprite_item_id", path.stem)  # type: ignore[attr-defined]

    @staticmethod
    def _handle_sprite_disconnected(in_port: object) -> None:
        """Clear the sprite when a SpriteNode is disconnected."""
        target = in_port.node()  # type: ignore[attr-defined]
        target.clear_sprite()  # type: ignore[attr-defined]
        if target.get_widget("sprite_item_id") is not None:  # type: ignore[attr-defined]
            target.set_property("sprite_item_id", "")  # type: ignore[attr-defined]

    # -- Variable node handlers -----------------------------------------------

    def _handle_variable_connected(
        self,
        in_port: object,
        out_port: object,
    ) -> None:
        """Handle a variable node connecting to a field_* input port."""
        source_node = out_port.node()  # type: ignore[attr-defined]
        consumer_node = in_port.node()  # type: ignore[attr-defined]

        # Only variable nodes may connect to field_* ports
        if not getattr(source_node, "IS_VARIABLE", False):
            with self._guard():
                in_port.disconnect_from(out_port)  # type: ignore[attr-defined]
            return

        port_name: str = in_port.name()  # type: ignore[attr-defined]
        field_name = port_name.removeprefix("field_")

        # Type-safety check
        fp = consumer_node._get_field_pin(field_name)
        if fp is None:
            return

        var_fp = source_node._get_field_pin("value")
        if var_fp is None:
            return

        if fp.pin_type != var_fp.pin_type:
            with self._guard():
                in_port.disconnect_from(out_port)  # type: ignore[attr-defined]
            return

        # Stash current value and disable widget
        current_value = consumer_node.get_property(field_name)
        consumer_node._stashed_values[field_name] = current_value
        consumer_node.disable_field(field_name)

        # Push variable value to model
        var_value = source_node.get_property("value")

        from craftgraph.pin_registry import convert_to_model

        converted = convert_to_model(fp, var_value)
        model = consumer_node.model_ref
        if model is not None:
            model_attr = fp.resolved_model_field

            from craftgraph.commands import ChangeNonRecipeFieldCommand, ChangeRecipeFieldCommand
            from craftgraph.models import ModifiedRecipe

            if isinstance(model, ModifiedRecipe):
                cmd = ChangeRecipeFieldCommand(model, model_attr, converted)
            else:
                cmd = ChangeNonRecipeFieldCommand(model, model_attr, converted)
            with self._guard():
                self._history.execute(cmd)

        # Mirror the variable value in the disabled widget
        from craftgraph.pin_registry import convert_to_display

        consumer_node._populating = True
        try:
            consumer_node.set_property(field_name, convert_to_display(fp, converted))
        finally:
            consumer_node._populating = False

    def _handle_variable_disconnected(
        self,
        in_port: object,
        out_port: object,
    ) -> None:
        """Handle a variable node disconnecting from a field_* input port."""
        consumer_node = in_port.node()  # type: ignore[attr-defined]

        port_name: str = in_port.name()  # type: ignore[attr-defined]
        field_name = port_name.removeprefix("field_")

        # Re-enable widget
        consumer_node.enable_field(field_name)

        # Restore stashed value
        stashed = consumer_node._stashed_values.pop(field_name, None)
        if stashed is None:
            return

        fp = consumer_node._get_field_pin(field_name)
        if fp is None:
            return

        # Push stashed value back to model
        from craftgraph.pin_registry import convert_to_model

        converted = convert_to_model(fp, stashed)
        model = consumer_node.model_ref
        if model is not None:
            model_attr = fp.resolved_model_field

            from craftgraph.commands import ChangeNonRecipeFieldCommand, ChangeRecipeFieldCommand
            from craftgraph.models import ModifiedRecipe

            if isinstance(model, ModifiedRecipe):
                cmd = ChangeRecipeFieldCommand(model, model_attr, converted)
            else:
                cmd = ChangeNonRecipeFieldCommand(model, model_attr, converted)
            with self._guard():
                self._history.execute(cmd)

        # Update widget display
        consumer_node._populating = True
        try:
            consumer_node.set_property(field_name, stashed)
        finally:
            consumer_node._populating = False

    def _handle_variable_value_changed(
        self,
        var_node: BaseNode,
        new_value: object,
    ) -> None:
        """Propagate a variable node's value to all connected consumer fields."""
        value_out = var_node.get_output("value_out")  # type: ignore[attr-defined]
        if value_out is None:
            return

        from craftgraph.pin_registry import convert_to_display, convert_to_model

        for connected_port in value_out.connected_ports():
            consumer_node = connected_port.node()
            port_name: str = connected_port.name()
            if not port_name.startswith("field_"):
                continue

            field_name = port_name.removeprefix("field_")
            fp = consumer_node._get_field_pin(field_name)
            if fp is None:
                continue

            converted = convert_to_model(fp, new_value)
            model = consumer_node.model_ref
            if model is None:
                continue

            model_attr = fp.resolved_model_field

            from craftgraph.commands import ChangeNonRecipeFieldCommand, ChangeRecipeFieldCommand
            from craftgraph.models import ModifiedRecipe

            if isinstance(model, ModifiedRecipe):
                cmd = ChangeRecipeFieldCommand(model, model_attr, converted)
            else:
                cmd = ChangeNonRecipeFieldCommand(model, model_attr, converted)

            with self._guard():
                self._history.execute(cmd)

            # Mirror the value in the disabled widget
            consumer_node._populating = True
            try:
                consumer_node.set_property(field_name, convert_to_display(fp, converted))
            finally:
                consumer_node._populating = False

    # -- Helpers --------------------------------------------------------------

    def _find_parsed_file_for(self, model_obj: object) -> ParsedFile | None:
        """Find the ParsedFile that contains *model_obj* (identity check)."""
        for pf in self._parsed_files:
            for recipe in pf.all_recipes:
                if recipe is model_obj:
                    return pf
            for fab in pf.custom_fabricators:
                if fab is model_obj:
                    return pf
            for tab in pf.crafting_tabs:
                if tab is model_obj:
                    return pf
            for size in pf.custom_sizes:
                if size is model_obj:
                    return pf
            for moved in pf.moved_recipes:
                if moved is model_obj:
                    return pf
            for fuel in pf.custom_bio_fuels:
                if fuel is model_obj:
                    return pf
            for frag in pf.custom_fragment_counts:
                if frag is model_obj:
                    return pf
        return None
