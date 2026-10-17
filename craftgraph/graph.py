"""Dependency graph builder and cycle detection.

Builds a NetworkX DiGraph from parsed CC3 recipe files. Each node is an
item ID (the crafted result or a raw ingredient). Directed edges represent
dependency: an edge from A to B means "A requires B as an ingredient".

Node classification:
    - RAW_MATERIAL: has outgoing edges (is used by recipes) but no incoming
      edges (is not itself crafted). Leaf nodes in the dependency tree.
    - END_PRODUCT: has incoming edges (crafts from ingredients) but no
      outgoing edges (nothing else uses it).
    - INTERMEDIATE: has both incoming and outgoing edges.
"""

from enum import Enum
from typing import cast

import networkx as nx

from craftgraph.models import (
    AddedRecipe,
    AliasRecipe,
    CustomFood,
    ModifiedRecipe,
    ParsedFile,
)


class NodeType(Enum):
    """Classification of a node's role in the dependency graph."""

    RAW_MATERIAL = "raw_material"
    INTERMEDIATE = "intermediate"
    END_PRODUCT = "end_product"


def _recipe_type_label(recipe: ModifiedRecipe) -> str:
    """Return a human-readable label for the recipe's type."""
    if isinstance(recipe, CustomFood):
        return "CustomFood"
    if isinstance(recipe, AliasRecipe):
        return "AliasRecipe"
    if isinstance(recipe, AddedRecipe):
        return "AddedRecipe"
    return "ModifiedRecipe"


def build_graph(parsed_files: list[ParsedFile]) -> nx.DiGraph[str]:
    """Build a dependency graph from parsed CC3 recipe files.

    Nodes represent unique item IDs across all files. Each node carries
    metadata attributes:

    - ``recipe_type``: the CC3 recipe type (e.g. "ModifiedRecipe")
    - ``source_file``: path of the file the recipe was parsed from
    - ``is_crafted``: True if this item appears as a recipe output

    Edges represent dependency: an edge ``(A, B)`` means item A requires
    item B as an ingredient.

    Items that appear only as ingredients (never as a recipe output) are
    added as nodes with ``is_crafted=False``.
    """
    graph: nx.DiGraph[str] = nx.DiGraph()

    for parsed_file in parsed_files:
        for recipe in parsed_file.all_recipes:
            item_id = recipe.item_id

            # Add or update the recipe node
            if item_id not in graph:
                graph.add_node(
                    item_id,
                    recipe_type=_recipe_type_label(recipe),
                    source_file=str(parsed_file.source_path),
                    is_crafted=True,
                )
            else:
                # Node already exists (maybe as an ingredient-only node),
                # update its metadata to reflect that it is also crafted.
                graph.nodes[item_id]["is_crafted"] = True
                graph.nodes[item_id]["recipe_type"] = _recipe_type_label(recipe)
                graph.nodes[item_id]["source_file"] = str(parsed_file.source_path)

            # Add edges to each ingredient
            for ingredient in recipe.ingredients:
                ing_id = ingredient.item_id
                if ing_id not in graph:
                    graph.add_node(ing_id, is_crafted=False)
                graph.add_edge(
                    item_id,
                    ing_id,
                    required=ingredient.required,
                    edge_kind="ingredient",
                )

            # Unlocks: crafting this recipe reveals each listed TechType.
            # Direction matches ingredient (recipe -> target). Ingredient
            # wins on overlap so cycle detection and tooltips keep the
            # required-count metadata. Self-loops (Unlocks: <SelfID>) are
            # a known CC3 idiom (not a real dependency) and would falsely
            # trigger cycle detection -- skip them.
            for unlocked_id in recipe.unlocks:
                if unlocked_id == item_id:
                    continue
                if unlocked_id not in graph:
                    graph.add_node(unlocked_id, is_crafted=False)
                if graph.has_edge(item_id, unlocked_id):
                    continue
                graph.add_edge(item_id, unlocked_id, edge_kind="unlocks")

            # UnlockedBy: scanning any of these reveals this recipe.
            # Direction is reversed (source -> this recipe). Self-loops are
            # skipped for the same reason as Unlocks above.
            for unlocker_id in recipe.unlocked_by:
                if unlocker_id == item_id:
                    continue
                if unlocker_id not in graph:
                    graph.add_node(unlocker_id, is_crafted=False)
                if graph.has_edge(unlocker_id, item_id):
                    continue
                graph.add_edge(unlocker_id, item_id, edge_kind="unlocked_by")

    return graph


# -- Cycle detection -----------------------------------------------------------


_CYCLE_CACHE_KEY = "_cycle_cache"


def find_cycles(graph: nx.DiGraph[str]) -> list[list[str]]:
    """Find all simple cycles formed by *ingredient* edges.

    Only ingredient edges (``edge_kind == "ingredient"`` or unset, for
    backward compatibility with older code paths) participate in cycle
    detection. Unlock / UnlockedBy edges encode discovery requirements,
    not buildability constraints -- a recipe being unlocked by something
    doesn't prevent crafting it, so mixed-kind loops are not real cycles.

    Returns a list of cycles, where each cycle is a list of item IDs
    forming the circular path. Returns an empty list if the ingredient
    subgraph is acyclic.

    Results are memoized on the graph itself, keyed by ``(n_nodes, n_edges)``;
    a fresh ``build_graph`` call (or any add/remove that changes those
    counts) invalidates the cache.
    """
    key = (graph.number_of_nodes(), graph.number_of_edges())
    cached = graph.graph.get(_CYCLE_CACHE_KEY)
    if cached is not None and cached[0] == key:
        return cast("list[list[str]]", cached[1])
    ingredient_graph: nx.DiGraph[str] = nx.DiGraph()
    ingredient_graph.add_nodes_from(graph.nodes(data=True))
    for u, v, data in graph.edges(data=True):
        if data.get("edge_kind", "ingredient") == "ingredient":
            ingredient_graph.add_edge(u, v, **data)
    cycles = [list(cycle) for cycle in nx.simple_cycles(ingredient_graph)]
    graph.graph[_CYCLE_CACHE_KEY] = (key, cycles)
    return cycles


# -- Dependency query helpers --------------------------------------------------


def get_dependencies(graph: nx.DiGraph[str], item_id: str) -> set[str]:
    """Return the set of items that *item_id* directly requires.

    These are the successors in the graph (outgoing edges = ingredients).
    Returns an empty set if the item is not in the graph.
    """
    if item_id not in graph:
        return set()
    return set(graph.successors(item_id))


def get_dependents(graph: nx.DiGraph[str], item_id: str) -> set[str]:
    """Return the set of items that directly use *item_id* as an ingredient.

    These are the predecessors in the graph (incoming edges = recipes that
    need this item). Returns an empty set if the item is not in the graph.
    """
    if item_id not in graph:
        return set()
    return set(graph.predecessors(item_id))


def classify_nodes(graph: nx.DiGraph[str]) -> dict[str, NodeType]:
    """Classify every node in the graph by its structural role.

    - ``RAW_MATERIAL``: out-degree == 0 (has no ingredients; it's a leaf).
      Other recipes may use it (in-degree >= 0).
    - ``END_PRODUCT``: in-degree == 0 (nothing uses it as an ingredient)
      and out-degree > 0 (it does require ingredients).
    - ``INTERMEDIATE``: both in-degree > 0 and out-degree > 0 (it is crafted
      from ingredients AND is used as an ingredient by other recipes).
    """
    result: dict[str, NodeType] = {}
    for node in graph.nodes:
        has_incoming = graph.in_degree(node) > 0
        has_outgoing = graph.out_degree(node) > 0

        if has_incoming and has_outgoing:
            result[node] = NodeType.INTERMEDIATE
        elif has_outgoing:
            result[node] = NodeType.END_PRODUCT
        else:
            result[node] = NodeType.RAW_MATERIAL

    return result
