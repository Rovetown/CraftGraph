"""Tests for the dependency graph builder.

Tests cover:
- build_graph: node creation, edge creation, metadata, cross-file references
- find_cycles: acyclic graphs, single cycle, multiple cycles, self-loops
- get_dependencies / get_dependents: query helpers
- classify_nodes: raw material, intermediate, end product classification
"""

from pathlib import Path

import networkx as nx

from craftgraph.graph import (
    NodeType,
    build_graph,
    classify_nodes,
    find_cycles,
    get_dependencies,
    get_dependents,
)
from craftgraph.models import (
    AddedRecipe,
    AliasRecipe,
    BlockType,
    CustomFood,
    Ingredient,
    ModifiedRecipe,
    ParsedFile,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_parsed_file(
    recipes: list[ModifiedRecipe],
    *,
    path: str = "test.txt",
    block_type: BlockType = BlockType.MODIFIED_RECIPES,
) -> ParsedFile:
    """Create a ParsedFile populated with the given recipes."""
    pf = ParsedFile(source_path=Path(path), block_type=block_type)
    for recipe in recipes:
        if isinstance(recipe, CustomFood):
            pf.custom_foods.append(recipe)
        elif isinstance(recipe, AliasRecipe):
            pf.alias_recipes.append(recipe)
        elif isinstance(recipe, AddedRecipe):
            pf.added_recipes.append(recipe)
        else:
            pf.modified_recipes.append(recipe)
    return pf


# ---------------------------------------------------------------------------
# build_graph -- basic structure
# ---------------------------------------------------------------------------


class TestBuildGraphBasic:
    """Test fundamental graph construction from recipes."""

    def test_empty_input(self) -> None:
        graph = build_graph([])
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    def test_single_recipe_creates_nodes(self) -> None:
        """A recipe with one ingredient creates 2 nodes and 1 edge."""
        recipe = ModifiedRecipe(
            item_id="Titanium",
            ingredients=[Ingredient("ScrapMetal", 1)],
        )
        graph = build_graph([_make_parsed_file([recipe])])
        assert "Titanium" in graph.nodes
        assert "ScrapMetal" in graph.nodes
        assert len(graph.nodes) == 2

    def test_single_recipe_creates_edge(self) -> None:
        recipe = ModifiedRecipe(
            item_id="Titanium",
            ingredients=[Ingredient("ScrapMetal", 1)],
        )
        graph = build_graph([_make_parsed_file([recipe])])
        assert graph.has_edge("Titanium", "ScrapMetal")
        assert graph.edges["Titanium", "ScrapMetal"]["required"] == 1

    def test_multiple_ingredients(self) -> None:
        recipe = ModifiedRecipe(
            item_id="FiberMesh",
            ingredients=[
                Ingredient("CreepvinePiece", 1),
                Ingredient("PurpleFanSeed", 1),
            ],
        )
        graph = build_graph([_make_parsed_file([recipe])])
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2
        assert graph.has_edge("FiberMesh", "CreepvinePiece")
        assert graph.has_edge("FiberMesh", "PurpleFanSeed")

    def test_multiple_recipes_shared_ingredient(self) -> None:
        """Two recipes sharing an ingredient don't duplicate the node."""
        recipes = [
            ModifiedRecipe(
                item_id="Glass",
                ingredients=[Ingredient("Quartz", 5)],
            ),
            ModifiedRecipe(
                item_id="EnameledGlass",
                ingredients=[
                    Ingredient("Glass", 3),
                    Ingredient("Quartz", 2),
                ],
            ),
        ]
        graph = build_graph([_make_parsed_file(recipes)])
        assert len(graph.nodes) == 3  # Glass, EnameledGlass, Quartz
        assert graph.has_edge("Glass", "Quartz")
        assert graph.has_edge("EnameledGlass", "Glass")
        assert graph.has_edge("EnameledGlass", "Quartz")
        # Glass is both a recipe output and an ingredient
        assert graph.nodes["Glass"]["is_crafted"] is True

    def test_recipe_no_ingredients(self) -> None:
        """A recipe with no ingredients creates only the recipe node."""
        recipe = ModifiedRecipe(item_id="EmptyRecipe")
        graph = build_graph([_make_parsed_file([recipe])])
        assert len(graph.nodes) == 1
        assert "EmptyRecipe" in graph.nodes
        assert len(graph.edges) == 0


# ---------------------------------------------------------------------------
# build_graph -- node metadata
# ---------------------------------------------------------------------------


class TestBuildGraphMetadata:
    """Test that nodes carry correct metadata attributes."""

    def test_crafted_node_has_metadata(self) -> None:
        recipe = ModifiedRecipe(
            item_id="Titanium",
            ingredients=[Ingredient("ScrapMetal", 1)],
        )
        graph = build_graph([_make_parsed_file([recipe], path="recipes.txt")])
        node = graph.nodes["Titanium"]
        assert node["is_crafted"] is True
        assert node["recipe_type"] == "ModifiedRecipe"
        assert node["source_file"] == "recipes.txt"

    def test_ingredient_only_node_not_crafted(self) -> None:
        recipe = ModifiedRecipe(
            item_id="Titanium",
            ingredients=[Ingredient("ScrapMetal", 1)],
        )
        graph = build_graph([_make_parsed_file([recipe])])
        node = graph.nodes["ScrapMetal"]
        assert node["is_crafted"] is False

    def test_ingredient_upgraded_to_crafted(self) -> None:
        """If an ingredient later appears as a recipe output, is_crafted updates."""
        recipes = [
            ModifiedRecipe(
                item_id="EnameledGlass",
                ingredients=[Ingredient("Glass", 3)],
            ),
            ModifiedRecipe(
                item_id="Glass",
                ingredients=[Ingredient("Quartz", 5)],
            ),
        ]
        graph = build_graph([_make_parsed_file(recipes)])
        assert graph.nodes["Glass"]["is_crafted"] is True
        assert graph.nodes["Glass"]["recipe_type"] == "ModifiedRecipe"

    def test_recipe_type_added(self) -> None:
        recipe = AddedRecipe(item_id="BigWater", path="Fab/Water")
        pf = _make_parsed_file([recipe], block_type=BlockType.ADDED_RECIPES)
        graph = build_graph([pf])
        assert graph.nodes["BigWater"]["recipe_type"] == "AddedRecipe"

    def test_recipe_type_alias(self) -> None:
        recipe = AliasRecipe(
            item_id="Seat",
            display_name="Seamoth Seat",
            tooltip="A seat",
        )
        pf = _make_parsed_file([recipe], block_type=BlockType.ALIAS_RECIPES)
        graph = build_graph([pf])
        assert graph.nodes["Seat"]["recipe_type"] == "AliasRecipe"

    def test_recipe_type_custom_food(self) -> None:
        recipe = CustomFood(
            item_id="Burger",
            display_name="Burger",
            tooltip="Tasty",
            food_value=20,
        )
        pf = _make_parsed_file([recipe], block_type=BlockType.CUSTOM_FOODS)
        graph = build_graph([pf])
        assert graph.nodes["Burger"]["recipe_type"] == "CustomFood"

    def test_edge_required_count(self) -> None:
        recipe = ModifiedRecipe(
            item_id="Glass",
            ingredients=[Ingredient("Quartz", 5)],
        )
        graph = build_graph([_make_parsed_file([recipe])])
        assert graph.edges["Glass", "Quartz"]["required"] == 5


# ---------------------------------------------------------------------------
# build_graph -- cross-file
# ---------------------------------------------------------------------------


class TestBuildGraphCrossFile:
    """Test graph construction across multiple parsed files."""

    def test_cross_file_references(self) -> None:
        """Items referenced across two files are unified in the graph."""
        file1 = _make_parsed_file(
            [
                ModifiedRecipe(
                    item_id="Glass",
                    ingredients=[Ingredient("Quartz", 5)],
                ),
            ],
            path="file1.txt",
        )
        file2 = _make_parsed_file(
            [
                ModifiedRecipe(
                    item_id="EnameledGlass",
                    ingredients=[Ingredient("Glass", 3)],
                ),
            ],
            path="file2.txt",
        )
        graph = build_graph([file1, file2])
        assert len(graph.nodes) == 3  # Glass, Quartz, EnameledGlass
        assert graph.has_edge("Glass", "Quartz")
        assert graph.has_edge("EnameledGlass", "Glass")
        # Glass was defined in file1 but referenced as ingredient in file2
        assert graph.nodes["Glass"]["is_crafted"] is True
        assert graph.nodes["Glass"]["source_file"] == "file1.txt"


# ---------------------------------------------------------------------------
# Unlock relationships
# ---------------------------------------------------------------------------


class TestBuildGraphUnlocks:
    """Unlocks / UnlockedBy emit distinct edges tagged with edge_kind.

    Direction: ``recipe.unlocks = [B]`` -> edge ``recipe -> B``
               ``recipe.unlocked_by = [B]`` -> edge ``B -> recipe``
    """

    def test_ingredient_edges_carry_kind_attribute(self) -> None:
        """Existing ingredient edges gain edge_kind='ingredient'."""
        recipe = ModifiedRecipe(
            item_id="Titanium",
            ingredients=[Ingredient("ScrapMetal", 1)],
        )
        graph = build_graph([_make_parsed_file([recipe])])
        assert graph.edges["Titanium", "ScrapMetal"]["edge_kind"] == "ingredient"

    def test_unlocks_creates_forward_edge(self) -> None:
        """recipe.unlocks=[B] yields recipe -> B with edge_kind='unlocks'."""
        recipe = ModifiedRecipe(item_id="Knife", unlocks=["Spear", "Sword"])
        graph = build_graph([_make_parsed_file([recipe])])
        assert graph.has_edge("Knife", "Spear")
        assert graph.edges["Knife", "Spear"]["edge_kind"] == "unlocks"
        assert graph.has_edge("Knife", "Sword")
        assert graph.edges["Knife", "Sword"]["edge_kind"] == "unlocks"

    def test_unlocked_by_creates_reverse_edge(self) -> None:
        """recipe.unlocked_by=[B] yields B -> recipe with edge_kind='unlocked_by'."""
        recipe = ModifiedRecipe(item_id="Sword", unlocked_by=["Knife"])
        graph = build_graph([_make_parsed_file([recipe])])
        assert graph.has_edge("Knife", "Sword")
        assert graph.edges["Knife", "Sword"]["edge_kind"] == "unlocked_by"

    def test_unlock_target_added_as_node_if_missing(self) -> None:
        """Items referenced only by unlocks still appear as nodes (is_crafted=False)."""
        recipe = ModifiedRecipe(item_id="Knife", unlocks=["Spear"])
        graph = build_graph([_make_parsed_file([recipe])])
        assert "Spear" in graph.nodes
        assert graph.nodes["Spear"]["is_crafted"] is False

    def test_ingredient_takes_precedence_over_unlock(self) -> None:
        """If an ingredient edge already exists, an overlapping unlock edge is skipped."""
        recipe = ModifiedRecipe(
            item_id="Hybrid",
            ingredients=[Ingredient("Titanium", 1)],
            unlocks=["Titanium"],
        )
        graph = build_graph([_make_parsed_file([recipe])])
        # The pair only has one edge, kept as ingredient.
        assert graph.edges["Hybrid", "Titanium"]["edge_kind"] == "ingredient"
        assert graph.edges["Hybrid", "Titanium"]["required"] == 1

    def test_unlocks_self_does_not_create_edge(self) -> None:
        """A recipe with Unlocks: <self_id> is a CC3 idiom, not a dependency.

        The graph must not contain the A -> A self-loop or false cycles would
        be reported.  Ingredient self-loops are a different case and stay
        cycle-flagged via test_self_loop in TestFindCycles.
        """
        recipe = ModifiedRecipe(item_id="Alch_Lab", unlocks=["Alch_Lab"])
        graph = build_graph([_make_parsed_file([recipe])])
        assert not graph.has_edge("Alch_Lab", "Alch_Lab")

    def test_unlocked_by_self_does_not_create_edge(self) -> None:
        """A recipe with UnlockedBy: <self_id> does not create a self-loop either."""
        recipe = ModifiedRecipe(item_id="Alch_Lab", unlocked_by=["Alch_Lab"])
        graph = build_graph([_make_parsed_file([recipe])])
        assert not graph.has_edge("Alch_Lab", "Alch_Lab")

    def test_unlocks_self_is_not_reported_as_cycle(self) -> None:
        """The self-unlock idiom never appears in find_cycles output."""
        recipe = ModifiedRecipe(item_id="Alch_Lab", unlocks=["Alch_Lab"])
        graph = build_graph([_make_parsed_file([recipe])])
        cycles = find_cycles(graph)
        assert all("Alch_Lab" not in c or len(c) != 1 for c in cycles)


# ---------------------------------------------------------------------------
# find_cycles
# ---------------------------------------------------------------------------


class TestFindCycles:
    """Test cycle detection in the dependency graph."""

    def test_acyclic_graph(self) -> None:
        """No cycles in a simple linear dependency chain."""
        recipes = [
            ModifiedRecipe(
                item_id="TitaniumIngot",
                ingredients=[Ingredient("Titanium", 10)],
            ),
            ModifiedRecipe(
                item_id="Titanium",
                ingredients=[Ingredient("ScrapMetal", 1)],
            ),
        ]
        graph = build_graph([_make_parsed_file(recipes)])
        assert find_cycles(graph) == []

    def test_simple_cycle(self) -> None:
        """A -> B -> A creates one cycle."""
        recipes = [
            ModifiedRecipe(
                item_id="A",
                ingredients=[Ingredient("B", 1)],
            ),
            ModifiedRecipe(
                item_id="B",
                ingredients=[Ingredient("A", 1)],
            ),
        ]
        graph = build_graph([_make_parsed_file(recipes)])
        cycles = find_cycles(graph)
        assert len(cycles) == 1
        assert set(cycles[0]) == {"A", "B"}

    def test_three_node_cycle(self) -> None:
        """A -> B -> C -> A creates one cycle."""
        recipes = [
            ModifiedRecipe(item_id="A", ingredients=[Ingredient("B", 1)]),
            ModifiedRecipe(item_id="B", ingredients=[Ingredient("C", 1)]),
            ModifiedRecipe(item_id="C", ingredients=[Ingredient("A", 1)]),
        ]
        graph = build_graph([_make_parsed_file(recipes)])
        cycles = find_cycles(graph)
        assert len(cycles) == 1
        assert set(cycles[0]) == {"A", "B", "C"}

    def test_self_loop(self) -> None:
        """An item that requires itself is a cycle of length 1."""
        recipe = ModifiedRecipe(
            item_id="Ouroboros",
            ingredients=[Ingredient("Ouroboros", 1)],
        )
        graph = build_graph([_make_parsed_file([recipe])])
        cycles = find_cycles(graph)
        assert len(cycles) == 1
        assert cycles[0] == ["Ouroboros"]

    def test_multiple_independent_cycles(self) -> None:
        """Two separate cycles are both detected."""
        recipes = [
            # Cycle 1: X <-> Y
            ModifiedRecipe(item_id="X", ingredients=[Ingredient("Y", 1)]),
            ModifiedRecipe(item_id="Y", ingredients=[Ingredient("X", 1)]),
            # Cycle 2: P <-> Q
            ModifiedRecipe(item_id="P", ingredients=[Ingredient("Q", 1)]),
            ModifiedRecipe(item_id="Q", ingredients=[Ingredient("P", 1)]),
        ]
        graph = build_graph([_make_parsed_file(recipes)])
        cycles = find_cycles(graph)
        assert len(cycles) == 2
        cycle_sets = [set(c) for c in cycles]
        assert {"X", "Y"} in cycle_sets
        assert {"P", "Q"} in cycle_sets

    def test_cycle_with_non_cyclic_branches(self) -> None:
        """A cycle exists alongside non-cyclic nodes."""
        recipes = [
            # Linear chain: D -> E (no cycle)
            ModifiedRecipe(item_id="D", ingredients=[Ingredient("E", 1)]),
            # Cycle: A -> B -> A
            ModifiedRecipe(item_id="A", ingredients=[Ingredient("B", 1)]),
            ModifiedRecipe(item_id="B", ingredients=[Ingredient("A", 1)]),
        ]
        graph = build_graph([_make_parsed_file(recipes)])
        cycles = find_cycles(graph)
        assert len(cycles) == 1
        assert set(cycles[0]) == {"A", "B"}

    def test_empty_graph(self) -> None:
        graph = build_graph([])
        assert find_cycles(graph) == []


# ---------------------------------------------------------------------------
# get_dependencies / get_dependents
# ---------------------------------------------------------------------------


class TestDependencyQueries:
    """Test get_dependencies and get_dependents helpers."""

    def _build_sample_graph(self) -> nx.DiGraph[str]:
        """Build a small graph: EnameledGlass -> Glass -> Quartz."""
        recipes = [
            ModifiedRecipe(
                item_id="Glass",
                ingredients=[Ingredient("Quartz", 5)],
            ),
            ModifiedRecipe(
                item_id="EnameledGlass",
                ingredients=[
                    Ingredient("Glass", 3),
                    Ingredient("Diamond", 1),
                ],
            ),
        ]
        return build_graph([_make_parsed_file(recipes)])

    def test_get_dependencies(self) -> None:
        graph = self._build_sample_graph()
        assert get_dependencies(graph, "EnameledGlass") == {"Glass", "Diamond"}

    def test_get_dependencies_leaf(self) -> None:
        graph = self._build_sample_graph()
        assert get_dependencies(graph, "Quartz") == set()

    def test_get_dependencies_unknown_node(self) -> None:
        graph = self._build_sample_graph()
        assert get_dependencies(graph, "NotInGraph") == set()

    def test_get_dependents(self) -> None:
        graph = self._build_sample_graph()
        assert get_dependents(graph, "Glass") == {"EnameledGlass"}

    def test_get_dependents_root(self) -> None:
        graph = self._build_sample_graph()
        assert get_dependents(graph, "EnameledGlass") == set()

    def test_get_dependents_unknown_node(self) -> None:
        graph = self._build_sample_graph()
        assert get_dependents(graph, "NotInGraph") == set()

    def test_get_dependents_shared_ingredient(self) -> None:
        """An ingredient used by multiple recipes returns all of them."""
        recipes = [
            ModifiedRecipe(item_id="A", ingredients=[Ingredient("Shared", 1)]),
            ModifiedRecipe(item_id="B", ingredients=[Ingredient("Shared", 1)]),
            ModifiedRecipe(item_id="C", ingredients=[Ingredient("Shared", 1)]),
        ]
        graph = build_graph([_make_parsed_file(recipes)])
        assert get_dependents(graph, "Shared") == {"A", "B", "C"}


# ---------------------------------------------------------------------------
# classify_nodes
# ---------------------------------------------------------------------------


class TestClassifyNodes:
    """Test node classification into raw material, intermediate, end product."""

    def test_simple_chain(self) -> None:
        """EnameledGlass -> Glass -> Quartz classifies correctly."""
        recipes = [
            ModifiedRecipe(
                item_id="Glass",
                ingredients=[Ingredient("Quartz", 5)],
            ),
            ModifiedRecipe(
                item_id="EnameledGlass",
                ingredients=[Ingredient("Glass", 3)],
            ),
        ]
        graph = build_graph([_make_parsed_file(recipes)])
        types = classify_nodes(graph)
        assert types["Quartz"] == NodeType.RAW_MATERIAL
        assert types["Glass"] == NodeType.INTERMEDIATE
        assert types["EnameledGlass"] == NodeType.END_PRODUCT

    def test_all_raw_materials(self) -> None:
        """A recipe with only raw ingredients: recipe is end product, rest raw."""
        recipe = ModifiedRecipe(
            item_id="FiberMesh",
            ingredients=[
                Ingredient("CreepvinePiece", 1),
                Ingredient("PurpleFanSeed", 1),
            ],
        )
        graph = build_graph([_make_parsed_file([recipe])])
        types = classify_nodes(graph)
        assert types["CreepvinePiece"] == NodeType.RAW_MATERIAL
        assert types["PurpleFanSeed"] == NodeType.RAW_MATERIAL
        assert types["FiberMesh"] == NodeType.END_PRODUCT

    def test_isolated_node(self) -> None:
        """A recipe with no ingredients is classified as RAW_MATERIAL (no edges)."""
        recipe = ModifiedRecipe(item_id="Lonely")
        graph = build_graph([_make_parsed_file([recipe])])
        types = classify_nodes(graph)
        assert types["Lonely"] == NodeType.RAW_MATERIAL

    def test_diamond_shape(self) -> None:
        """Diamond-shaped dependency graph."""
        recipes = [
            ModifiedRecipe(
                item_id="Final",
                ingredients=[Ingredient("Mid1", 1), Ingredient("Mid2", 1)],
            ),
            ModifiedRecipe(item_id="Mid1", ingredients=[Ingredient("Raw", 1)]),
            ModifiedRecipe(item_id="Mid2", ingredients=[Ingredient("Raw", 1)]),
        ]
        graph = build_graph([_make_parsed_file(recipes)])
        types = classify_nodes(graph)
        assert types["Raw"] == NodeType.RAW_MATERIAL
        assert types["Mid1"] == NodeType.INTERMEDIATE
        assert types["Mid2"] == NodeType.INTERMEDIATE
        assert types["Final"] == NodeType.END_PRODUCT

    def test_empty_graph(self) -> None:
        graph = build_graph([])
        assert classify_nodes(graph) == {}

    def test_cyclic_nodes_are_intermediate(self) -> None:
        """Nodes in a cycle have both incoming and outgoing edges."""
        recipes = [
            ModifiedRecipe(item_id="A", ingredients=[Ingredient("B", 1)]),
            ModifiedRecipe(item_id="B", ingredients=[Ingredient("A", 1)]),
        ]
        graph = build_graph([_make_parsed_file(recipes)])
        types = classify_nodes(graph)
        assert types["A"] == NodeType.INTERMEDIATE
        assert types["B"] == NodeType.INTERMEDIATE


# ---------------------------------------------------------------------------
# Cycle detection cache
# ---------------------------------------------------------------------------


class TestFindCyclesCache:
    """find_cycles memoizes results on the graph until topology changes."""

    def test_repeated_call_skips_recomputation(self, monkeypatch) -> None:
        recipes = [
            ModifiedRecipe(item_id="A", ingredients=[Ingredient("B", 1)]),
            ModifiedRecipe(item_id="B", ingredients=[Ingredient("A", 1)]),
        ]
        graph = build_graph([_make_parsed_file(recipes)])

        first = find_cycles(graph)

        # After the first call, simple_cycles must not be invoked again
        # for an unchanged graph -- the result comes from the cache.
        from craftgraph import graph as graph_mod

        sentinel_calls = 0

        def boom(_g):
            nonlocal sentinel_calls
            sentinel_calls += 1
            return iter(())

        monkeypatch.setattr(graph_mod.nx, "simple_cycles", boom)
        second = find_cycles(graph)

        assert sentinel_calls == 0, "cached result must short-circuit simple_cycles"
        assert second == first

    def test_topology_change_invalidates_cache(self) -> None:
        recipes = [
            ModifiedRecipe(item_id="A", ingredients=[Ingredient("B", 1)]),
            ModifiedRecipe(item_id="B", ingredients=[Ingredient("A", 1)]),
        ]
        graph = build_graph([_make_parsed_file(recipes)])

        first = find_cycles(graph)
        assert first  # non-empty: A <-> B cycle

        # Break the cycle by removing one edge -- the cache must invalidate
        # so the next call returns the now-empty cycle list.
        graph.remove_edge("A", "B")
        second = find_cycles(graph)
        assert second == []
