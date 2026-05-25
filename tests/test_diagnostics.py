"""Tests for the project-issues data layer.

Covers :func:`craftgraph.diagnostics.find_project_issues` -- the pure (no Qt)
analyzer that powers the Project Issues window. Categories asserted:

- **Orphans**: recipes nobody references.
- **Cycles**: ingredient / unlock loops.
- **Unresolved references**: ingredient / unlocks / unlocked_by / linked_item_ids
  pointing at an ID that is neither defined by the project nor a known vanilla
  TechType.
"""

from __future__ import annotations

from pathlib import Path

from craftgraph.diagnostics import (
    CycleIssue,
    OrphanIssue,
    ProjectIssues,
    UnresolvedRefIssue,
    find_project_issues,
)
from craftgraph.models import (
    AddedRecipe,
    BlockType,
    Ingredient,
    ModifiedRecipe,
    ParsedFile,
)


def _pf(recipes: list[ModifiedRecipe], *, name: str = "t.txt") -> ParsedFile:
    """Build a ParsedFile of ModifiedRecipes containing *recipes*."""
    pf = ParsedFile(source_path=Path(name), block_type=BlockType.MODIFIED_RECIPES)
    for r in recipes:
        if isinstance(r, AddedRecipe):
            pf.added_recipes.append(r)
        else:
            pf.modified_recipes.append(r)
    return pf


# ---------------------------------------------------------------------------
# Aggregate shape
# ---------------------------------------------------------------------------


def test_returns_project_issues_dataclass() -> None:
    result = find_project_issues([])
    assert isinstance(result, ProjectIssues)
    assert result.orphans == []
    assert result.cycles == []
    assert result.unresolved_refs == []


# ---------------------------------------------------------------------------
# Orphans -- recipes with zero incoming edges
# ---------------------------------------------------------------------------


class TestOrphans:
    """Orphan = truly isolated recipe: no incoming AND no outgoing edges.

    A recipe with ingredients (out_degree > 0) is still useful even if
    nothing references it -- it's the end product of a craft chain.
    Only completely-disconnected recipes are flagged.
    """

    def test_recipe_with_ingredients_is_not_orphan(self) -> None:
        """A recipe with ingredients but no one referencing it is NOT orphan."""
        recipes = [
            ModifiedRecipe(item_id="Titanium"),
            ModifiedRecipe(
                item_id="Bar", ingredients=[Ingredient("Titanium", 1)],
            ),
        ]
        result = find_project_issues([_pf(recipes)])
        orphan_ids = [o.item_id for o in result.orphans]
        # Bar has out_degree > 0 (-> Titanium) so it is connected; not orphan.
        assert "Bar" not in orphan_ids
        # Titanium has in_degree > 0 (Bar -> Titanium); not orphan.
        assert "Titanium" not in orphan_ids

    def test_isolated_recipe_is_orphan(self) -> None:
        """A recipe with no ingredients AND no one referencing it IS an orphan."""
        recipes = [ModifiedRecipe(item_id="Loner")]
        result = find_project_issues([_pf(recipes)])
        assert any(o.item_id == "Loner" for o in result.orphans)

    def test_recipe_referenced_by_unlocks_is_not_orphan(self) -> None:
        recipes = [
            ModifiedRecipe(item_id="Sword"),
            ModifiedRecipe(item_id="Knife", unlocks=["Sword"]),
        ]
        result = find_project_issues([_pf(recipes)])
        assert not any(o.item_id == "Sword" for o in result.orphans)
        # Knife has outgoing edge to Sword, also not orphan.
        assert not any(o.item_id == "Knife" for o in result.orphans)

    def test_recipe_with_unlocked_by_is_not_orphan(self) -> None:
        """unlocked_by points at THIS recipe; the source becomes a predecessor."""
        recipes = [
            ModifiedRecipe(item_id="Hidden", unlocked_by=["Knife"]),
        ]
        result = find_project_issues([_pf(recipes)])
        # Hidden has Knife -> Hidden incoming edge, so Hidden is not orphan.
        assert not any(o.item_id == "Hidden" for o in result.orphans)

    def test_orphan_carries_source_file(self) -> None:
        recipes = [ModifiedRecipe(item_id="Lonely")]
        result = find_project_issues([_pf(recipes, name="lonely.txt")])
        assert result.orphans
        assert result.orphans[0].item_id == "Lonely"
        assert result.orphans[0].source_file.endswith("lonely.txt")


# ---------------------------------------------------------------------------
# Cycles
# ---------------------------------------------------------------------------


class TestCycles:
    def test_no_cycle_returns_empty(self) -> None:
        recipes = [
            ModifiedRecipe(
                item_id="Bar", ingredients=[Ingredient("Titanium", 1)],
            ),
        ]
        assert find_project_issues([_pf(recipes)]).cycles == []

    def test_simple_two_node_cycle_detected(self) -> None:
        recipes = [
            ModifiedRecipe(
                item_id="A", ingredients=[Ingredient("B", 1)],
            ),
            ModifiedRecipe(
                item_id="B", ingredients=[Ingredient("A", 1)],
            ),
        ]
        result = find_project_issues([_pf(recipes)])
        assert len(result.cycles) == 1
        assert set(result.cycles[0].items) == {"A", "B"}

    def test_cycle_through_unlocks_not_detected(self) -> None:
        """Unlock edges do NOT participate in cycle detection.

        Unlock cycles are not unbuildability bugs -- a recipe being unlocked
        by something else doesn't prevent crafting it. Only ingredient cycles
        are flagged.
        """
        recipes = [
            ModifiedRecipe(item_id="A", unlocks=["B"]),
            ModifiedRecipe(item_id="B", unlocks=["A"]),
        ]
        result = find_project_issues([_pf(recipes)])
        assert result.cycles == []

    def test_mixed_ingredient_and_unlocked_by_is_not_a_cycle(self) -> None:
        """Real-world: a recipe with ingredient Y AND UnlockedBy Y is buildable.

        Scanning / obtaining Y satisfies the unlock condition, and the same Y
        becomes the ingredient. Mirrors Alch_MercuryOre + Lithium from real
        mod data, which used to surface as a false cycle.
        """
        recipes = [
            ModifiedRecipe(
                item_id="Alch_MercuryOre",
                ingredients=[Ingredient("Lithium", 1)],
                unlocked_by=["Lithium"],
            ),
        ]
        result = find_project_issues([_pf(recipes)])
        assert result.cycles == []


# ---------------------------------------------------------------------------
# Unresolved references
# ---------------------------------------------------------------------------


class TestUnresolvedRefs:
    KNOWN = frozenset({"titanium", "quartz", "computerchip"})

    def test_unknown_ingredient_flagged(self) -> None:
        recipes = [
            ModifiedRecipe(
                item_id="Widget", ingredients=[Ingredient("NotAThing", 1)],
            ),
        ]
        result = find_project_issues([_pf(recipes)], known_extra_ids=self.KNOWN)
        refs = [(r.ref_type, r.target) for r in result.unresolved_refs]
        assert ("ingredient", "NotAThing") in refs

    def test_known_vanilla_id_not_flagged(self) -> None:
        """An ingredient that matches a known ID is not flagged."""
        recipes = [
            ModifiedRecipe(
                item_id="Widget", ingredients=[Ingredient("Titanium", 1)],
            ),
        ]
        result = find_project_issues([_pf(recipes)], known_extra_ids=self.KNOWN)
        assert not result.unresolved_refs

    def test_project_defined_id_not_flagged(self) -> None:
        """An ingredient whose ID is defined as a recipe in the project is not flagged."""
        recipes = [
            ModifiedRecipe(item_id="MyAlloy"),
            ModifiedRecipe(
                item_id="Widget", ingredients=[Ingredient("MyAlloy", 1)],
            ),
        ]
        result = find_project_issues([_pf(recipes)], known_extra_ids=self.KNOWN)
        assert not result.unresolved_refs

    def test_unknown_in_unlocks_flagged_with_kind(self) -> None:
        recipes = [
            ModifiedRecipe(item_id="Widget", unlocks=["FakeID"]),
        ]
        result = find_project_issues([_pf(recipes)], known_extra_ids=self.KNOWN)
        refs = [(r.ref_type, r.target) for r in result.unresolved_refs]
        assert ("unlocks", "FakeID") in refs

    def test_unknown_in_unlocked_by_flagged_with_kind(self) -> None:
        recipes = [
            ModifiedRecipe(item_id="Widget", unlocked_by=["GhostID"]),
        ]
        result = find_project_issues([_pf(recipes)], known_extra_ids=self.KNOWN)
        refs = [(r.ref_type, r.target) for r in result.unresolved_refs]
        assert ("unlocked_by", "GhostID") in refs

    def test_unknown_in_linked_item_ids_flagged(self) -> None:
        recipes = [
            ModifiedRecipe(item_id="Widget", linked_item_ids=["NopeID"]),
        ]
        result = find_project_issues([_pf(recipes)], known_extra_ids=self.KNOWN)
        refs = [(r.ref_type, r.target) for r in result.unresolved_refs]
        assert ("linked_item_ids", "NopeID") in refs

    def test_case_insensitive_match(self) -> None:
        """Known IDs match case-insensitively (CC3 itself is case-insensitive)."""
        recipes = [
            ModifiedRecipe(
                item_id="Widget", ingredients=[Ingredient("TITANIUM", 1)],
            ),
        ]
        result = find_project_issues([_pf(recipes)], known_extra_ids=self.KNOWN)
        assert not result.unresolved_refs

    def test_unresolved_ref_carries_owner_and_source(self) -> None:
        recipes = [
            ModifiedRecipe(
                item_id="Widget", ingredients=[Ingredient("Bogus", 1)],
            ),
        ]
        result = find_project_issues(
            [_pf(recipes, name="mod.txt")], known_extra_ids=self.KNOWN,
        )
        issue = result.unresolved_refs[0]
        assert isinstance(issue, UnresolvedRefIssue)
        assert issue.item_id == "Widget"
        assert issue.target == "Bogus"
        assert issue.ref_type == "ingredient"
        assert issue.source_file.endswith("mod.txt")


# ---------------------------------------------------------------------------
# Integration with the committed mini fixture
# ---------------------------------------------------------------------------


def test_mini_fixture_is_clean() -> None:
    """Running diagnostics on tests/fixtures/mini_mod/ produces zero issues.

    Every recipe in the mini fixture has at least one ingredient (out_degree > 0),
    so no recipe is fully isolated -- the orphan list is empty under the new
    "truly isolated only" definition.
    """
    from craftgraph.parser import parse_directory

    fixture = Path(__file__).resolve().parent / "fixtures" / "mini_mod"
    parsed = parse_directory(fixture)
    result = find_project_issues(parsed)

    assert result.cycles == []
    assert result.unresolved_refs == []
    assert result.orphans == []


# ---------------------------------------------------------------------------
# OrphanIssue / CycleIssue are simple dataclasses
# ---------------------------------------------------------------------------


def test_issue_dataclasses_are_equatable() -> None:
    """Issue dataclasses should compare structurally so callers can dedupe."""
    a = OrphanIssue(item_id="X", source_file="t.txt")
    b = OrphanIssue(item_id="X", source_file="t.txt")
    assert a == b
    c = CycleIssue(items=["A", "B"])
    d = CycleIssue(items=["A", "B"])
    assert c == d
