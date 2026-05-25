"""Integration tests against the tracked mini recipe fixture.

The fixture under ``tests/fixtures/mini_mod/`` is the only set of CC3 recipe
files guaranteed to exist on every clone -- the broader ``cc3_reference_files/``
tree is gitignored. These tests ensure:

  - Every fixture file parses cleanly (no ParseError / MappingError).
  - The parser covers every block type the fixture exercises.
  - parse -> serialize -> parse roundtrips per file.
  - The combined dependency graph builds without cycles.
  - The graph contains the expected items and edges (regression guard).

Keep new fixture files small and well-formatted. The integration suite
relies on the fixture being small enough to assert on exhaustively.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from craftgraph.graph import build_graph, find_cycles
from craftgraph.models import BlockType
from craftgraph.parser import parse_directory, parse_file
from craftgraph.serializer import serialize_file

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "mini_mod"


@pytest.fixture(scope="module")
def parsed_files():
    files = parse_directory(FIXTURE_DIR)
    assert files, f"Mini fixture is empty: {FIXTURE_DIR}"
    return files


# ---------------------------------------------------------------------------
# Structural assertions
# ---------------------------------------------------------------------------


def test_fixture_dir_exists() -> None:
    assert FIXTURE_DIR.is_dir(), (
        f"Mini fixture must be tracked in git at {FIXTURE_DIR}. "
        "If it was deleted, restore it from git."
    )


def test_expected_files_present() -> None:
    expected = {
        "mini_modified.txt",
        "mini_added.txt",
        "mini_alias.txt",
        "mini_fabricator.txt",
        "mini_sizes.txt",
    }
    actual = {p.name for p in FIXTURE_DIR.glob("*.txt")}
    assert expected.issubset(actual), f"missing fixture files: {expected - actual}"


def test_block_types_covered(parsed_files) -> None:
    """Every fixture file resolves to its declared block type."""
    by_name = {pf.source_path.name: pf for pf in parsed_files}
    assert by_name["mini_modified.txt"].block_type is BlockType.MODIFIED_RECIPES
    assert by_name["mini_added.txt"].block_type is BlockType.ADDED_RECIPES
    assert by_name["mini_alias.txt"].block_type is BlockType.ALIAS_RECIPES
    assert by_name["mini_fabricator.txt"].block_type is BlockType.CUSTOM_FABRICATORS
    assert by_name["mini_sizes.txt"].block_type is BlockType.CUSTOM_SIZES


# ---------------------------------------------------------------------------
# Per-file content asserts (regression guards on the fixture itself)
# ---------------------------------------------------------------------------


def test_modified_recipes_content() -> None:
    pf = parse_file(FIXTURE_DIR / "mini_modified.txt")
    assert [r.item_id for r in pf.modified_recipes] == [
        "GlassPipe",
        "ReinforcedDiveSuit",
    ]
    glass_pipe = pf.modified_recipes[0]
    assert [(i.item_id, i.required) for i in glass_pipe.ingredients] == [
        ("Titanium", 2),
        ("Quartz", 1),
    ]
    dive_suit = pf.modified_recipes[1]
    assert dive_suit.force_unlock_at_start is True


def test_added_recipe_content() -> None:
    pf = parse_file(FIXTURE_DIR / "mini_added.txt")
    assert len(pf.added_recipes) == 1
    rod = pf.added_recipes[0]
    assert rod.item_id == "DepletedReactorRod"
    assert rod.path == "Fabricator/Resources/Electronics"
    assert rod.force_unlock_at_start is False
    assert rod.linked_item_ids == ["UraniniteCrystal", "UraniniteCrystal"]


def test_alias_recipe_content() -> None:
    pf = parse_file(FIXTURE_DIR / "mini_alias.txt")
    assert len(pf.alias_recipes) == 1
    gallon = pf.alias_recipes[0]
    assert gallon.display_name == "Water Jug - 1 gallon"
    assert gallon.tooltip == "Large water jug for storage"
    assert gallon.path == "Fabricator/Survival/Water"


def test_fabricator_content() -> None:
    pf = parse_file(FIXTURE_DIR / "mini_fabricator.txt")
    assert len(pf.custom_fabricators) == 1
    fab = pf.custom_fabricators[0]
    assert fab.item_id == "SampleFab"
    assert fab.model == "Workbench"
    assert len(fab.tabs) == 1
    assert fab.tabs[0].tab_id == "ScienceTab"
    assert len(fab.added_recipes) == 1
    assert fab.added_recipes[0].item_id == "LabEquipment1"


def test_sizes_content() -> None:
    pf = parse_file(FIXTURE_DIR / "mini_sizes.txt")
    sizes = {s.item_id: (s.width, s.height) for s in pf.custom_sizes}
    assert sizes == {"GlassPipe": (1, 2), "ReinforcedDiveSuit": (2, 2)}


# ---------------------------------------------------------------------------
# Roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "mini_modified.txt",
        "mini_added.txt",
        "mini_alias.txt",
        "mini_fabricator.txt",
        "mini_sizes.txt",
    ],
)
def test_roundtrip_per_file(name: str, tmp_path: Path) -> None:
    """parse -> serialize -> parse must yield identical ParsedFile (minus path)."""
    src = FIXTURE_DIR / name
    original = parse_file(src)

    out = tmp_path / name
    out.write_text(serialize_file(original), encoding="utf-8")
    reparsed = parse_file(out)

    # source_path will differ; clear it so the structural compare works.
    original.source_path = out
    assert reparsed == original


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def test_graph_builds_without_cycles(parsed_files) -> None:
    graph = build_graph(parsed_files)
    assert graph.number_of_nodes() > 0
    assert find_cycles(graph) == []


def test_graph_contains_expected_edges(parsed_files) -> None:
    graph = build_graph(parsed_files)
    # GlassPipe depends on Titanium + Quartz
    assert graph.has_edge("GlassPipe", "Titanium")
    assert graph.has_edge("GlassPipe", "Quartz")
    # DepletedReactorRod depends on ReactorRod
    assert graph.has_edge("DepletedReactorRod", "ReactorRod")
    # GallonWater depends on DisinfectedWater
    assert graph.has_edge("GallonWater", "DisinfectedWater")
