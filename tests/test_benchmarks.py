"""pytest-benchmark baselines for the parser / serializer / graph hot paths.

These are not regression-gating asserts -- ``test_perf_stress.py`` already
caps the Tier A folder load at 10s with cProfile. The purpose here is a
*tracked* baseline (mean / stddev / min) so a future change that moves
parser timing in either direction is visible in CI output, and saved
runs can be compared with ``--benchmark-compare`` over time.

Tagged ``@pytest.mark.slow`` so the default sweep stays fast. Run with::

    just test-slow tests/test_benchmarks.py --benchmark-only

The Tier B / A workloads live under ``cc3_reference_files`` which is
gitignored; benchmarks self-skip when the folder is missing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from craftgraph.graph import build_graph
from craftgraph.parser import parse_directory, parse_file, parse_text
from craftgraph.serializer import serialize_file

pytestmark = pytest.mark.slow


_REPO_ROOT = Path(__file__).resolve().parent.parent
_REF = _REPO_ROOT / "craftgraph" / "cc3_reference_files"
_TIER_B = _REF / "original-source" / "CustomCraft3" / "SampleFiles" / "EquipmentSalvage"
_TIER_A = _REF / "real-mod-examples"
_MINI = Path(__file__).resolve().parent / "fixtures" / "mini_mod"


def _skip_if_missing(folder: Path) -> None:
    if not folder.exists():
        pytest.skip(f"workload missing (gitignored): {folder}")


# ---------------------------------------------------------------------------
# Mini tier (tracked fixture, always available)
# ---------------------------------------------------------------------------


def test_parse_mini_folder(benchmark) -> None:
    """Recursive parse of the tracked mini fixture (5 files)."""
    parsed = benchmark(parse_directory, _MINI)
    assert parsed


def test_serialize_mini_files(benchmark) -> None:
    parsed_files = parse_directory(_MINI)

    def serialize_all() -> int:
        return sum(len(serialize_file(pf)) for pf in parsed_files)

    assert benchmark(serialize_all) > 0


def test_build_graph_mini(benchmark) -> None:
    parsed_files = parse_directory(_MINI)
    graph = benchmark(build_graph, parsed_files)
    assert graph.number_of_nodes() > 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parse_tier_a_folder(benchmark) -> None:
    """Recursive parse of the Tier A real-mod set (~50 files)."""
    _skip_if_missing(_TIER_A)
    parsed = benchmark(parse_directory, _TIER_A)
    assert parsed, "Tier A parse returned no files"


def test_parse_tier_b_folder(benchmark) -> None:
    """Recursive parse of the small EquipmentSalvage sample set."""
    _skip_if_missing(_TIER_B)
    parsed = benchmark(parse_directory, _TIER_B)
    assert parsed, "Tier B parse returned no files"


def test_parse_single_file(benchmark, tmp_path) -> None:
    """Single-file parse on a synthetic in-memory recipe set.

    Independent of cc3_reference_files availability so the benchmark
    always has at least one data point.
    """
    text = "\n".join(
        ["ModifiedRecipes:"]
        + ["("]
        + ["    ItemID: TitaniumIngot;"]
        + ["    AmountCrafted: 1;"]
        + ["    Ingredients:"]
        + ["    ( ItemID: Titanium; Required: 10; );"]
        + ["),"] * 0
        + [");"]
    )
    src = tmp_path / "bench.txt"
    src.write_text(text, encoding="utf-8")
    parsed = benchmark(parse_file, src)
    assert parsed.block_type is not None


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------


def test_serialize_tier_a_files(benchmark) -> None:
    """Serialize every parsed Tier A file back to text."""
    _skip_if_missing(_TIER_A)
    parsed_files = parse_directory(_TIER_A)

    def serialize_all() -> int:
        return sum(len(serialize_file(pf)) for pf in parsed_files)

    total = benchmark(serialize_all)
    assert total > 0


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def test_build_graph_tier_a(benchmark) -> None:
    """Build the NetworkX dependency graph from Tier A recipes."""
    _skip_if_missing(_TIER_A)
    parsed_files = parse_directory(_TIER_A)
    graph = benchmark(build_graph, parsed_files)
    assert graph.number_of_nodes() > 0


# ---------------------------------------------------------------------------
# Roundtrip
# ---------------------------------------------------------------------------


def test_parse_serialize_roundtrip_tier_a(benchmark) -> None:
    """Full parse -> serialize -> parse pipeline on the Tier A set."""
    _skip_if_missing(_TIER_A)
    parsed_files = parse_directory(_TIER_A)

    def roundtrip() -> int:
        n = 0
        for pf in parsed_files:
            text = serialize_file(pf)
            if not text:
                continue
            reparsed = parse_text(text, source_path=pf.source_path)
            n += len(reparsed.all_recipes) if hasattr(reparsed, "all_recipes") else 0
        return n

    benchmark(roundtrip)
