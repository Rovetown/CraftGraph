"""Unit tests for sync.apply_file_diff -- per-tab diff apply layer."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("NodeGraphQt")


from craftgraph.model_diff import FileDiff
from craftgraph.models import Ingredient, ModifiedRecipe, ParsedFile


@pytest.fixture
def graph(qapp, qtbot):
    from craftgraph.qt_nodes import all_node_classes
    from NodeGraphQt import NodeGraph

    g = NodeGraph()
    g.set_acyclic(False)
    for cls in all_node_classes():
        g.register_node(cls)
    qtbot.addWidget(g.widget)
    return g


def _make_tab(graph, parsed_file=None, model_to_node=None):
    """Build a minimal FileTab-like stand-in for the apply layer tests.

    The real FileTab requires editor + history + ui_handler etc., none of
    which apply_file_diff touches. A simple namespace with the four fields
    apply_file_diff actually reads is sufficient.
    """
    from types import SimpleNamespace

    from craftgraph.sync import SyncGuard

    return SimpleNamespace(
        graph=graph,
        parsed_file=parsed_file,
        model_to_node=model_to_node if model_to_node is not None else {},
        sync_guard=SyncGuard(),
    )


class TestApplyFileDiffScaffold:
    def test_empty_diff_is_noop(self, graph):
        from craftgraph.sync import apply_file_diff

        old_pf = ParsedFile(source_path=Path("smoke.txt"))
        tab = _make_tab(graph, parsed_file=old_pf)

        new_pf = ParsedFile(source_path=Path("smoke.txt"))
        result = apply_file_diff(
            file_tab=tab,
            diff=FileDiff(added=[], removed=[], modified=[]),
            new_parsed_file=new_pf,
        )
        assert result.nodes_created == []
        assert result.nodes_deleted_ids == []
        assert result.nodes_modified == []
        assert tab.parsed_file is new_pf


class TestApplyRemovePass:
    def test_removes_node_for_removed_recipe(self, graph):
        """A removed entry deletes its node from the graph and from model_to_node."""
        from craftgraph.qt_nodes import IDENTIFIER
        from craftgraph.sync import apply_file_diff

        recipe = ModifiedRecipe(item_id="Titanium")
        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        node.model_ref = recipe
        old_pf = ParsedFile(source_path=Path("f.txt"))
        old_pf.modified_recipes.append(recipe)
        tab = _make_tab(graph, parsed_file=old_pf, model_to_node={id(recipe): node})

        new_pf = ParsedFile(source_path=Path("f.txt"))
        diff = FileDiff(added=[], removed=[recipe], modified=[])

        node_id = node.id
        result = apply_file_diff(file_tab=tab, diff=diff, new_parsed_file=new_pf)

        assert id(recipe) not in tab.model_to_node
        assert node_id not in {n.id for n in graph.all_nodes()}
        assert result.nodes_deleted_ids == [node_id]

    def test_removes_multiple_nodes(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER
        from craftgraph.sync import apply_file_diff

        r1 = ModifiedRecipe(item_id="Alpha")
        r2 = ModifiedRecipe(item_id="Beta")
        n1 = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        n2 = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        n1.model_ref = r1
        n2.model_ref = r2

        old_pf = ParsedFile(source_path=Path("f.txt"))
        old_pf.modified_recipes.extend([r1, r2])
        tab = _make_tab(
            graph,
            parsed_file=old_pf,
            model_to_node={id(r1): n1, id(r2): n2},
        )

        new_pf = ParsedFile(source_path=Path("f.txt"))
        diff = FileDiff(added=[], removed=[r1, r2], modified=[])

        result = apply_file_diff(file_tab=tab, diff=diff, new_parsed_file=new_pf)

        assert tab.model_to_node == {}
        assert len(result.nodes_deleted_ids) == 2

    def test_remove_with_missing_model_to_node_entry_is_safe(self, graph):
        """Drift between model and graph: pop returns None, no crash."""
        from craftgraph.sync import apply_file_diff

        ghost = ModifiedRecipe(item_id="Ghost")
        old_pf = ParsedFile(source_path=Path("f.txt"))
        tab = _make_tab(graph, parsed_file=old_pf, model_to_node={})

        new_pf = ParsedFile(source_path=Path("f.txt"))
        diff = FileDiff(added=[], removed=[ghost], modified=[])

        result = apply_file_diff(file_tab=tab, diff=diff, new_parsed_file=new_pf)

        assert result.nodes_deleted_ids == []


class TestApplyAddPass:
    def test_added_recipe_creates_node(self, graph):
        from craftgraph.sync import apply_file_diff

        old_pf = ParsedFile(source_path=Path("f.txt"))
        tab = _make_tab(graph, parsed_file=old_pf)

        new_recipe = ModifiedRecipe(item_id="Titanium")
        new_pf = ParsedFile(source_path=Path("f.txt"))
        new_pf.modified_recipes.append(new_recipe)
        diff = FileDiff(added=[new_recipe], removed=[], modified=[])

        result = apply_file_diff(file_tab=tab, diff=diff, new_parsed_file=new_pf)

        assert id(new_recipe) in tab.model_to_node
        node = tab.model_to_node[id(new_recipe)]
        assert node.model_ref is new_recipe
        assert result.nodes_created == [node]

    def test_added_alias_recipe_uses_alias_node(self, graph):
        from craftgraph.models import AliasRecipe
        from craftgraph.qt_nodes import AliasRecipeNode
        from craftgraph.sync import apply_file_diff

        old_pf = ParsedFile(source_path=Path("f.txt"))
        tab = _make_tab(graph, parsed_file=old_pf)

        alias = AliasRecipe(item_id="MyAlias", display_name="My Alias")
        new_pf = ParsedFile(source_path=Path("f.txt"))
        new_pf.alias_recipes.append(alias)
        diff = FileDiff(added=[alias], removed=[], modified=[])

        apply_file_diff(file_tab=tab, diff=diff, new_parsed_file=new_pf)
        node = tab.model_to_node[id(alias)]
        assert isinstance(node, AliasRecipeNode)

    def test_added_fabricator_uses_fab_node(self, graph):
        from craftgraph.models import CustomFabricator
        from craftgraph.qt_nodes import FabricatorNode
        from craftgraph.sync import apply_file_diff

        old_pf = ParsedFile(source_path=Path("f.txt"))
        tab = _make_tab(graph, parsed_file=old_pf)

        fab = CustomFabricator(item_id="MyFab")
        new_pf = ParsedFile(source_path=Path("f.txt"))
        new_pf.custom_fabricators.append(fab)
        diff = FileDiff(added=[fab], removed=[], modified=[])

        apply_file_diff(file_tab=tab, diff=diff, new_parsed_file=new_pf)
        assert isinstance(tab.model_to_node[id(fab)], FabricatorNode)


class TestApplyModifyPassFields:
    def test_modified_recipe_updates_widget_value(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER
        from craftgraph.sync import apply_file_diff

        old = ModifiedRecipe(item_id="Titanium", amount_crafted=1)
        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        node.model_ref = old
        node.populate_from_model()

        old_pf = ParsedFile(source_path=Path("f.txt"))
        old_pf.modified_recipes.append(old)
        tab = _make_tab(graph, parsed_file=old_pf, model_to_node={id(old): node})

        new = ModifiedRecipe(item_id="Titanium", amount_crafted=5)
        new_pf = ParsedFile(source_path=Path("f.txt"))
        new_pf.modified_recipes.append(new)
        diff = FileDiff(added=[], removed=[], modified=[(old, new)])

        result = apply_file_diff(file_tab=tab, diff=diff, new_parsed_file=new_pf)

        assert node.model_ref is new
        assert int(node.get_property("amount_crafted")) == 5
        assert result.nodes_modified == [node]
        assert id(new) in tab.model_to_node
        assert id(old) not in tab.model_to_node

    def test_modify_with_missing_node_is_safe(self, graph):
        from craftgraph.sync import apply_file_diff

        old = ModifiedRecipe(item_id="Titanium")
        new = ModifiedRecipe(item_id="Titanium", amount_crafted=2)

        old_pf = ParsedFile(source_path=Path("f.txt"))
        tab = _make_tab(graph, parsed_file=old_pf, model_to_node={})

        new_pf = ParsedFile(source_path=Path("f.txt"))
        diff = FileDiff(added=[], removed=[], modified=[(old, new)])

        result = apply_file_diff(file_tab=tab, diff=diff, new_parsed_file=new_pf)
        assert result.nodes_modified == []


class TestApplyModifyPassTopology:
    def test_ingredient_count_change_replaces_node(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER
        from craftgraph.sync import apply_file_diff

        old = ModifiedRecipe(
            item_id="Titanium",
            amount_crafted=1,
            ingredients=[Ingredient("Lithium", 1)],
        )
        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        node.model_ref = old
        old_pf = ParsedFile(source_path=Path("f.txt"))
        old_pf.modified_recipes.append(old)
        tab = _make_tab(graph, parsed_file=old_pf, model_to_node={id(old): node})
        old_node_id = node.id

        new = ModifiedRecipe(
            item_id="Titanium",
            amount_crafted=1,
            ingredients=[
                Ingredient("Lithium", 1),
                Ingredient("Magnetite", 2),
            ],
        )
        new_pf = ParsedFile(source_path=Path("f.txt"))
        new_pf.modified_recipes.append(new)
        diff = FileDiff(added=[], removed=[], modified=[(old, new)])

        result = apply_file_diff(file_tab=tab, diff=diff, new_parsed_file=new_pf)

        # Old node ID is gone; a fresh node exists with model_ref=new.
        assert old_node_id not in {n.id for n in graph.all_nodes()}
        assert id(new) in tab.model_to_node
        new_node = tab.model_to_node[id(new)]
        assert new_node.model_ref is new
        assert result.nodes_deleted_ids == [old_node_id]
        assert new_node in result.nodes_created

    def test_linked_item_ids_change_replaces_node(self, graph):
        from craftgraph.qt_nodes import IDENTIFIER
        from craftgraph.sync import apply_file_diff

        old = ModifiedRecipe(item_id="Titanium", linked_item_ids=["A"])
        node = graph.create_node(f"{IDENTIFIER}.ModifiedRecipeNode")
        node.model_ref = old
        old_pf = ParsedFile(source_path=Path("f.txt"))
        old_pf.modified_recipes.append(old)
        tab = _make_tab(graph, parsed_file=old_pf, model_to_node={id(old): node})
        old_node_id = node.id

        new = ModifiedRecipe(item_id="Titanium", linked_item_ids=["A", "B"])
        new_pf = ParsedFile(source_path=Path("f.txt"))
        new_pf.modified_recipes.append(new)
        diff = FileDiff(added=[], removed=[], modified=[(old, new)])

        result = apply_file_diff(file_tab=tab, diff=diff, new_parsed_file=new_pf)

        assert old_node_id in result.nodes_deleted_ids
        assert id(new) in tab.model_to_node
