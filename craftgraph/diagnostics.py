"""Project-wide issue detection for the CraftGraph diagnostics window.

Pure (no Qt) data layer that scans a list of :class:`ParsedFile` and returns
a typed :class:`ProjectIssues` aggregating:

- **Orphans**: items defined as recipes that nothing else references (no
  ingredient, ``Unlocks``, ``UnlockedBy``, or ``LinkedItemIDs`` points at them).
  Often intentional end products; the GUI surfaces them informationally.
- **Cycles**: ingredient / unlock loops, as returned by
  :func:`craftgraph.graph.find_cycles`.
- **Unresolved references**: ingredient / ``Unlocks`` / ``UnlockedBy`` /
  ``LinkedItemIDs`` IDs that match neither a project-defined recipe nor a
  known vanilla TechType.  Catches typos that pass autocomplete because the
  user typed past the suggestion.

``Path`` validation is intentionally NOT covered here in the first pass --
the Qt validator already surfaces invalid paths visually via the orange
border.  Move ``_path_targets_from_parsed_files`` out of ``qt_gui.py`` if
that case needs to land here later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from craftgraph.graph import build_graph, find_cycles
from craftgraph.models import ModifiedRecipe, ParsedFile
from craftgraph.parser import collect_defined_ids
from craftgraph.vanilla_ids import load_mod_compat_ids, load_vanilla_ids


@dataclass(frozen=True, slots=True)
class OrphanIssue:
    """A recipe item that has no incoming edges of any kind."""

    item_id: str
    source_file: str


@dataclass(frozen=True, slots=True)
class CycleIssue:
    """A cycle path, ordered as returned by ``find_cycles``."""

    items: list[str]


@dataclass(frozen=True, slots=True)
class UnresolvedRefIssue:
    """An ID reference that doesn't resolve to any known item.

    ``ref_type`` is one of: ``"ingredient"``, ``"unlocks"``, ``"unlocked_by"``,
    ``"linked_item_ids"``.
    """

    item_id: str       # the recipe whose field contains the unresolved ref
    target: str        # the ID that couldn't be resolved
    ref_type: str
    source_file: str


@dataclass(slots=True)
class ProjectIssues:
    """Aggregated result of a project scan."""

    orphans: list[OrphanIssue] = field(default_factory=list)
    cycles: list[CycleIssue] = field(default_factory=list)
    unresolved_refs: list[UnresolvedRefIssue] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def find_project_issues(
    parsed_files: list[ParsedFile],
    *,
    known_extra_ids: frozenset[str] | None = None,
) -> ProjectIssues:
    """Scan *parsed_files* and return all detected issues.

    Args:
        parsed_files: Every file in the loaded project.
        known_extra_ids: Optional supplemental set of IDs to treat as known
            during unresolved-ref detection (case-insensitive).  Tests pass
            a small fixture set instead of loading the full vanilla list.
            When ``None``, the vanilla + mod-compat ID sets are loaded from
            ``craftgraph.vanilla_ids``.
    """
    result = ProjectIssues()
    if not parsed_files:
        return result

    graph = build_graph(parsed_files)

    # -- Orphans: truly isolated recipes (in_degree == 0 AND out_degree == 0)
    # A recipe with ingredients is still useful even if nothing references
    # it -- it's an end product. Only fully-disconnected recipes are flagged.
    source_by_id: dict[str, str] = {}
    for pf in parsed_files:
        for recipe in pf.all_recipes:
            source_by_id.setdefault(recipe.item_id, str(pf.source_path))

    for node_id in graph.nodes:
        attrs = graph.nodes[node_id]
        if not attrs.get("is_crafted"):
            continue
        if graph.in_degree(node_id) > 0 or graph.out_degree(node_id) > 0:
            continue
        result.orphans.append(
            OrphanIssue(
                item_id=node_id,
                source_file=source_by_id.get(node_id, ""),
            )
        )

    # -- Cycles -------------------------------------------------------------
    for cycle in find_cycles(graph):
        result.cycles.append(CycleIssue(items=list(cycle)))

    # -- Unresolved references ---------------------------------------------
    known: set[str] = set()
    if known_extra_ids is None:
        known |= load_vanilla_ids()
        known |= load_mod_compat_ids()
    else:
        known |= {i.lower() for i in known_extra_ids}
    known |= {i.lower() for i in collect_defined_ids(parsed_files)}

    for pf in parsed_files:
        for recipe in pf.all_recipes:
            _scan_unresolved(recipe, pf, known, result)

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scan_unresolved(
    recipe: ModifiedRecipe,
    pf: ParsedFile,
    known: set[str],
    result: ProjectIssues,
) -> None:
    """Append UnresolvedRefIssue entries for any unknown ID on *recipe*."""
    source = str(pf.source_path)

    for ing in recipe.ingredients:
        if ing.item_id.lower() not in known:
            result.unresolved_refs.append(
                UnresolvedRefIssue(
                    item_id=recipe.item_id,
                    target=ing.item_id,
                    ref_type="ingredient",
                    source_file=source,
                )
            )
    for ref_field, ref_type in (
        (recipe.unlocks, "unlocks"),
        (recipe.unlocked_by, "unlocked_by"),
        (recipe.linked_item_ids, "linked_item_ids"),
    ):
        for target in ref_field:
            if target.lower() not in known:
                result.unresolved_refs.append(
                    UnresolvedRefIssue(
                        item_id=recipe.item_id,
                        target=target,
                        ref_type=ref_type,
                        source_file=source,
                    )
                )
